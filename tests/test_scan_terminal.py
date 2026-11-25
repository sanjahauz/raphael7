"""The terminal report: the lines an integrator reads first are there."""

from pathlib import Path

from rich.console import Console

from raphael7.scan.report import scan_folder
from raphael7.scan.terminal import print_report

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def render(folder: Path) -> str:
    console = Console(width=200, color_system=None, record=True)
    print_report(scan_folder(folder), console)
    return console.export_text()


def test_samples_report():
    text = render(SAMPLES)
    assert "Messages found:              192" in text
    assert "Feeds:                        15" in text
    assert "Odd ones out:                 24" in text
    assert "  other-version              8" in text
    assert "MEDIX at HOSP_SOUTH" in text
    assert "ORU^R01  20 messages, version 2.3.1, 2.5" in text
    assert "sometimes filled: OBX-8 8/10" in text
    assert "closest: OLDHIS at HOSP_EAST, 94% same fields; they also fill MSH-18, PV1-20" in text
    assert "broken/truncated.hl7#1" in text
    assert "MEDIX at HOSP_SOUTH: terminator in 60 messages, 5 feeds" in text
    assert "MEDIX at HOSP_SOUTH: ZPI in 21 messages (ADT^A01, ADT^A08)" in text


def test_clean_folder_says_so(tmp_path):
    msh = "MSH|^~\\&|APP|HOSP|||20261124||ADT^A01|1|P|2.5\rPID|1||123\r"
    (tmp_path / "1.hl7").write_text(msh)
    text = render(tmp_path)
    assert "No odd ones out." in text
    assert "Z-segments: none" in text


def test_summary_numbers_line_up_past_ten_thousand():
    from raphael7.scan.terminal import _summary_line

    small = _summary_line("Files read", 179)
    large = _summary_line("Messages found", 10000)
    assert large.endswith("10,000")
    assert len(small) == len(large)
