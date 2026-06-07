from __future__ import annotations

import pytest

from jobhunter.application_tracker import (
    INITIAL_STATUS,
    STATUSES,
    Application,
    validate_status,
)


def test_initial_status_is_applied():
    assert INITIAL_STATUS == "applied"


def test_statuses_are_the_five_lifecycle_values():
    assert STATUSES == ("applied", "interviewing", "offer", "rejected", "withdrawn")


def test_validate_status_accepts_known_value():
    validate_status("interviewing")  # no raise


def test_validate_status_rejects_unknown_value():
    with pytest.raises(ValueError, match="unknown status"):
        validate_status("ghosted")


def test_application_dataclass_round_trips_to_dict():
    app = Application(
        id="11111111-1111-1111-1111-111111111111",
        slug="20260607T010101Z-acme",
        job_title="Senior Engineer",
        company="Acme",
        url="https://jobs.example/1",
        status="applied",
        notes=None,
        applied_at="2026-06-07T01:01:01Z",
        created_at="2026-06-07T01:01:01Z",
        updated_at="2026-06-07T01:01:01Z",
    )
    d = app.to_dict()
    assert d["job_title"] == "Senior Engineer"
    assert d["status"] == "applied"
    assert d["slug"] == "20260607T010101Z-acme"
