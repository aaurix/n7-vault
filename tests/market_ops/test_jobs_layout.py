from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_jobs_layout():
    jobs = ROOT / "scripts" / "jobs"
    assert (jobs / "job_auto_watchdog.sh").exists()
    assert (jobs / "job_monitor_health.sh").exists()
    assert (jobs / "job_scan_skills.sh").exists()
    assert (jobs / "job_update_skills_inventory.sh").exists()

    assert not (ROOT / "scripts" / "auto_watchdog.sh").exists()
    assert not (ROOT / "scripts" / "monitor_health.sh").exists()
    assert not (ROOT / "scripts" / "scan_skills.sh").exists()
    assert not (ROOT / "scripts" / "update_skills_inventory.sh").exists()
