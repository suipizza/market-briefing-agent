import json

from briefing import config, pipeline


def test_dry_run_does_not_overwrite_real_record(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    real = tmp_path / "2026-10-30.json"
    real.write_text(json.dumps({"run_date": "2026-10-30", "narrative": {"one_liner": "실제"}}))
    pipeline._save_run({"run_date": "2026-10-30", "narrative": None}, dry_run=True)
    assert json.loads(real.read_text())["narrative"] == {"one_liner": "실제"}
    assert (tmp_path / "2026-10-30.dryrun.json").exists()


def test_previous_snapshot_ignores_dryrun_and_side_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for name in ("2026-10-23.json", "2026-10-24.dryrun.json", "2026-10-24.notion.json"):
        (tmp_path / name).write_text("{}")
    from datetime import date
    assert pipeline.previous_snapshot(date(2026, 10, 30)).name == "2026-10-23.json"
