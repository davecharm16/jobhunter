from __future__ import annotations

import pytest
from tests.fake_application_store import FakeApplicationStore

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


def test_fake_store_create_sets_initial_status_and_history():
    store = FakeApplicationStore()
    app = store.create(slug="s1", job_title="Eng", company="Acme", url=None)
    assert app.status == "applied"
    assert app.id
    hist = store.history(app.id)
    assert len(hist) == 1
    assert hist[0].from_status is None
    assert hist[0].to_status == "applied"


def test_fake_store_get_by_slug():
    store = FakeApplicationStore()
    created = store.create(slug="s2", job_title="Eng", company=None, url=None)
    assert store.get_by_slug("s2").id == created.id
    assert store.get_by_slug("missing") is None


def test_fake_store_update_status_appends_history():
    store = FakeApplicationStore()
    app = store.create(slug="s3", job_title="Eng", company=None, url=None)
    updated = store.update(app.id, status="interviewing")
    assert updated.status == "interviewing"
    hist = store.history(app.id)
    assert [h.to_status for h in hist] == ["applied", "interviewing"]


def test_fake_store_update_notes_only_no_history_row():
    store = FakeApplicationStore()
    app = store.create(slug="s4", job_title="Eng", company=None, url=None)
    store.update(app.id, notes="Prep system design")
    assert store.get(app.id).notes == "Prep system design"
    assert len(store.history(app.id)) == 1  # notes-only change adds no history


def test_fake_store_list_filters_by_status():
    store = FakeApplicationStore()
    a = store.create(slug="a", job_title="A", company=None, url=None)
    store.create(slug="b", job_title="B", company=None, url=None)
    store.update(a.id, status="offer")
    assert {x.slug for x in store.list(status="offer")} == {"a"}
    assert len(store.list()) == 2
