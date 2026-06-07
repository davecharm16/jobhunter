"""Route tests for /api/applications using the in-memory fake store.

The real Postgres store is exercised separately in
test_application_store_pg.py (skipped without TEST_DATABASE_URL).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.fake_application_store import FakeApplicationStore

from jobhunter.web.api import create_app
from jobhunter.web.routes.applications import get_store


@pytest.fixture()
def client_and_store():
    store = FakeApplicationStore()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), store


def test_post_creates_application_at_applied(client_and_store):
    client, _ = client_and_store
    resp = client.post(
        "/api/applications",
        json={"slug": "20260607T010101Z-acme", "job_title": "Eng", "company": "Acme", "url": "https://x/1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "applied"
    assert body["job_title"] == "Eng"
    assert body["id"]


def test_post_is_idempotent_on_slug(client_and_store):
    client, _ = client_and_store
    first = client.post("/api/applications", json={"slug": "dup", "job_title": "Eng"}).json()
    resp = client.post("/api/applications", json={"slug": "dup", "job_title": "Eng"})
    assert resp.status_code == 200  # existing returned, not duplicated
    assert resp.json()["id"] == first["id"]


def test_patch_updates_status(client_and_store):
    client, _ = client_and_store
    app = client.post("/api/applications", json={"slug": "s", "job_title": "Eng"}).json()
    resp = client.patch(f"/api/applications/{app['id']}", json={"status": "interviewing"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "interviewing"


def test_patch_rejects_unknown_status(client_and_store):
    client, _ = client_and_store
    app = client.post("/api/applications", json={"slug": "s", "job_title": "Eng"}).json()
    resp = client.patch(f"/api/applications/{app['id']}", json={"status": "ghosted"})
    assert resp.status_code == 422


def test_patch_missing_application_is_404(client_and_store):
    client, _ = client_and_store
    resp = client.patch("/api/applications/nope", json={"notes": "x"})
    assert resp.status_code == 404


def test_get_lists_and_filters(client_and_store):
    client, _ = client_and_store
    a = client.post("/api/applications", json={"slug": "a", "job_title": "A"}).json()
    client.post("/api/applications", json={"slug": "b", "job_title": "B"})
    client.patch(f"/api/applications/{a['id']}", json={"status": "offer"})
    assert len(client.get("/api/applications").json()) == 2
    offers = client.get("/api/applications?status=offer").json()
    assert [x["slug"] for x in offers] == ["a"]


def test_get_one_includes_history(client_and_store):
    client, _ = client_and_store
    app = client.post("/api/applications", json={"slug": "s", "job_title": "Eng"}).json()
    client.patch(f"/api/applications/{app['id']}", json={"status": "interviewing"})
    body = client.get(f"/api/applications/{app['id']}").json()
    assert body["status"] == "interviewing"
    assert [h["to_status"] for h in body["history"]] == ["applied", "interviewing"]
