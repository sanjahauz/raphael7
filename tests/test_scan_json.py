"""JSON output: plain data, stable order, a clean example per shape."""

import json
from pathlib import Path

from raphael7.scan.json_report import FORMAT_VERSION, report_to_dict
from raphael7.scan.report import scan_folder

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_json_is_plain_and_stable():
    first = json.dumps(report_to_dict(scan_folder(SAMPLES)), ensure_ascii=False)
    second = json.dumps(report_to_dict(scan_folder(SAMPLES)), ensure_ascii=False)
    assert first == second
    data = json.loads(first)
    assert data["format_version"] == FORMAT_VERSION
    assert len(data["feeds"]) == 15


def test_example_is_not_a_broken_message():
    """Vendor A's results feed holds broken samples too; its example must be a clean one."""
    data = report_to_dict(scan_folder(SAMPLES))
    for feed in data["feeds"]:
        if feed["sender"]["application"] == "ADMITPRO" and feed["message_type"] == "ORU^R01":
            break
    main_shape = feed["shapes"][0]
    assert main_shape["example"].startswith("vendor-a/")
    assert {"position": "OBX-5", "filled": 24, "of": 25} in main_shape["sometimes_filled"]


def test_outliers_and_habits():
    data = report_to_dict(scan_folder(SAMPLES))
    truncated = None
    for outlier in data["outliers"]:
        if outlier["where"] == "broken/truncated.hl7#1":
            truncated = outlier
    assert truncated["reasons"][0]["code"] == "missing-fields"
    habit_codes = set()
    for habit in data["habits"]:
        habit_codes.add((habit["sender"]["application"], habit["code"]))
    assert habit_codes == {("MEDIX", "terminator")}
