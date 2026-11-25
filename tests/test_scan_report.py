"""The whole scan on the sample corpus, end to end."""

from pathlib import Path

from raphael7.scan.files import message_files
from raphael7.scan.report import scan_folder

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_scan_samples_counts():
    report = scan_folder(SAMPLES)
    assert report.file_count == len(message_files(SAMPLES))
    # 3 vendors x 5 message types (A01, A08, A03, ORM, ORU)
    assert len(report.feeds) == 15
    total = 0
    for feed in report.feeds:
        total += feed.message_count
    assert report.message_count == total


def test_an_empty_folder_gives_an_empty_report(tmp_path):
    report = scan_folder(tmp_path)
    assert report.file_count == 0
    assert report.message_count == 0
    assert report.feeds == []
    assert report.outliers == []
