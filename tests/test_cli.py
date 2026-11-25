import json
from pathlib import Path

from typer.testing import CliRunner

from raphael7 import __version__
from raphael7.cli import app

runner = CliRunner()
SAMPLES = Path(__file__).resolve().parent.parent / "samples"
CLEAN = "MSH|^~\\&|APP|HOSP|||20261124||ADT^A01|1|P|2.5\rPID|1||123\r"


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert "scan" in result.output


def test_scan_clean_folder_exits_zero(tmp_path):
    (tmp_path / "1.hl7").write_text(CLEAN)
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "No odd ones out." in result.output


def test_scan_samples_exits_one_with_odd_ones_out():
    result = runner.invoke(app, ["scan", str(SAMPLES)])
    assert result.exit_code == 1
    assert "24 odd ones out" in result.output


def test_scan_json(tmp_path):
    (tmp_path / "1.hl7").write_text(CLEAN)
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["messages"] == 1
    assert data["outliers"] == []


def test_scan_rejects_missing_folder(tmp_path):
    result = runner.invoke(app, ["scan", str(tmp_path / "nope")])
    assert result.exit_code == 2
