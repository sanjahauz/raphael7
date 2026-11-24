"""Reading a folder for scan: every file is yielded, even one with no message."""

from pathlib import Path

from raphael7.scan.files import MessageRef, message_files, scan_files

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

ADT = "MSH|^~\\&|APP|FAC|||20261124||ADT^A01|1|P|2.5\rPID|1||123\r"


def test_files_are_sorted_and_hidden_ones_skipped(tmp_path):
    (tmp_path / "b.hl7").write_text(ADT)
    (tmp_path / "a.txt").write_text(ADT)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c").write_text(ADT)
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref")

    names = []
    for path in message_files(tmp_path):
        names.append(path.relative_to(tmp_path).as_posix())
    assert names == ["a.txt", "b.hl7", "sub/c"]


def test_a_file_without_messages_is_still_reported(tmp_path):
    (tmp_path / "empty.hl7").write_bytes(b"")
    scanned = list(scan_files(tmp_path))
    assert len(scanned) == 1
    assert scanned[0].messages == ()
    codes = []
    for issue in scanned[0].issues:
        codes.append(issue.code)
    assert codes == ["empty"]


def test_a_batch_file_gives_one_ref_per_message():
    batch_files = []
    for scanned in scan_files(SAMPLES):
        if scanned.path.startswith("vendor-c/") and len(scanned.messages) > 1:
            batch_files.append(scanned)
    assert batch_files, "vendor C sends its ORU results as batch files"

    first = batch_files[0]
    refs = first.refs()
    assert len(refs) == len(first.messages)
    assert refs[0] == MessageRef(first.path, 1)
    assert str(refs[1]) == f"{first.path}#2"
