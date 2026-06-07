"""Real Postgres ApplicationStore tests.

Skipped unless TEST_DATABASE_URL is set, e.g.:
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \\
        python -m pytest tests/integration/test_application_store_pg.py -v

Each test runs in a transaction-isolated, truncated schema.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture()
def store():
    from jobhunter.application_store_pg import PostgresApplicationStore

    s = PostgresApplicationStore(DB_URL)
    with s._connect() as conn:  # noqa: SLF001 — test-only cleanup
        conn.execute("truncate application_status_history, applications cascade")
        conn.commit()
    return s


def test_create_then_get(store):
    app = store.create(slug="pg1", job_title="Eng", company="Acme", url="https://x/1")
    assert app.status == "applied"
    fetched = store.get(app.id)
    assert fetched.slug == "pg1"
    assert fetched.company == "Acme"


def test_get_by_slug(store):
    app = store.create(slug="pg2", job_title="Eng", company=None, url=None)
    assert store.get_by_slug("pg2").id == app.id
    assert store.get_by_slug("missing") is None


def test_create_writes_initial_history(store):
    app = store.create(slug="pg3", job_title="Eng", company=None, url=None)
    hist = store.history(app.id)
    assert len(hist) == 1 and hist[0].from_status is None and hist[0].to_status == "applied"


def test_update_status_appends_history(store):
    app = store.create(slug="pg4", job_title="Eng", company=None, url=None)
    store.update(app.id, status="interviewing")
    assert [h.to_status for h in store.history(app.id)] == ["applied", "interviewing"]


def test_update_notes_only_keeps_single_history_row(store):
    app = store.create(slug="pg5", job_title="Eng", company=None, url=None)
    store.update(app.id, notes="Prep")
    assert store.get(app.id).notes == "Prep"
    assert len(store.history(app.id)) == 1


def test_list_filters_by_status(store):
    a = store.create(slug="pga", job_title="A", company=None, url=None)
    store.create(slug="pgb", job_title="B", company=None, url=None)
    store.update(a.id, status="offer")
    assert {x.slug for x in store.list(status="offer")} == {"pga"}
    assert len(store.list()) == 2


def test_update_missing_returns_none(store):
    assert store.update("00000000-0000-0000-0000-000000000000", status="offer") is None


def test_malformed_id_is_treated_as_not_found(store):
    assert store.get("nope") is None
    assert store.update("nope", status="offer") is None
    assert store.history("nope") == []
