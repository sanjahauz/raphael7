"""The sample corpus: committed files match the generator, and the parser
reports exactly the issues each file is meant to produce."""

import importlib.util
import json
from pathlib import Path

import pytest

from raphael7.parser import parse_file

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def load_generator():
    """scripts/ is not a package, so load make_samples.py from its path."""
    path = ROOT / "scripts" / "make_samples.py"
    spec = importlib.util.spec_from_file_location("make_samples", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_samples = load_generator()
EXPECTED = json.loads((SAMPLES / make_samples.EXPECTED_ISSUES_FILE).read_text(encoding="utf-8"))

# Known parser gap: decode() reads MSH-18 only when the input starts with MSH.
# A batch file starts with FHS, so vendor C's 8859/8 Hebrew falls back to
# Latin-1 with a "decode" warning. strict=True: this fails once it is fixed.
KNOWN_GAPS = {
    path
    for path in EXPECTED
    if path.startswith("vendor-c/oru-batch-") or path == "broken/batch-count.hl7"
}


def test_committed_files_match_the_generator():
    """Run `uv run python scripts/make_samples.py` after changing the generator."""
    corpus = make_samples.build_corpus()
    on_disk = {}
    for folder in make_samples.GENERATED_DIRS:
        for path in sorted((SAMPLES / folder).rglob("*")):
            if path.is_file():
                on_disk[path.relative_to(SAMPLES).as_posix()] = path.read_bytes()
    assert sorted(on_disk) == sorted(corpus.files)
    for path, content in corpus.files.items():
        assert on_disk[path] == content, path
    assert corpus.expected_issues == EXPECTED


def issue_codes(path: Path) -> list[str]:
    """Every ParseIssue code for one file: input-level and per message."""
    result = parse_file(path)
    codes = set()
    for issue in result.issues:
        codes.add(issue.code)
    for message in result.messages:
        for issue in message.issues:
            codes.add(issue.code)
    return sorted(codes)


def issue_cases():
    cases = []
    for path, codes in sorted(EXPECTED.items()):
        marks = []
        if path in KNOWN_GAPS:
            marks.append(pytest.mark.xfail(strict=True, reason="MSH-18 not read in batch files"))
        cases.append(pytest.param(path, codes, id=path, marks=marks))
    return cases


@pytest.mark.parametrize(("path", "expected_codes"), issue_cases())
def test_parser_reports_the_expected_issues(path, expected_codes):
    assert issue_codes(SAMPLES / path) == expected_codes


def test_no_national_id_passes_the_check_digit():
    """No sample may carry an ID that could belong to a real person."""
    checked = 0
    for path in sorted(SAMPLES.glob("vendor-*/*.hl7")):
        for message in parse_file(path).messages:
            pid = next(segment for segment in message.segments if segment.id == "PID")
            for field_number in (2, 3):
                for repetition in pid.field(field_number):
                    value = repetition[0][0]
                    if len(value) == 9 and value.isdigit():
                        checked += 1
                        assert not make_samples.is_valid_israeli_id(value), path
    assert checked == 180  # one national ID per vendor message


def test_check_digit_rule_accepts_a_valid_id():
    """Guards the guard: 000000018 is the smallest valid teudat zehut."""
    assert make_samples.is_valid_israeli_id("000000018")
    assert not make_samples.is_valid_israeli_id("000000017")
