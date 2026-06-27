# tests/unit/test_scan_notification.py
from jobhunter.notifier import build_scan_message


def test_message_has_counts_and_dashboard_link_no_job_boards():
    msg = build_scan_message(
        new_count=5,
        site_summary={"indeed": {"status": "ok", "count": 3},
                      "linkedin": {"status": "blocked", "count": 0}},
        dashboard_url="http://127.0.0.1:8765/job-scan",
    )
    assert "5" in msg
    assert "127.0.0.1:8765/job-scan" in msg
    for host in ("indeed.com", "linkedin.com", "jobstreet.com", "onlinejobs.ph"):
        assert host not in msg


def test_message_lists_per_site_counts():
    msg = build_scan_message(
        new_count=3,
        site_summary={"indeed": {"status": "ok", "count": 3}},
        dashboard_url="http://127.0.0.1:8765/job-scan",
    )
    assert "indeed" in msg  # bare identifier, not a hostname
