"""Route tests for /api/applications using the in-memory fake store.

The real Postgres store is exercised separately in
test_application_store_pg.py (skipped without TEST_DATABASE_URL).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.fake_application_store import FakeApplicationStore

from jobhunter.web.api import create_app
from jobhunter.web.routes import package as package_module
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


def test_get_malformed_id_is_404(client_and_store):
    client, _ = client_and_store
    resp = client.get("/api/applications/not-a-uuid")
    assert resp.status_code == 404


def _stage_package(out_root: Path, slug: str, *, cv: str, cover: str) -> None:
    pkg = out_root / slug
    pkg.mkdir(parents=True)
    (pkg / "cv.md").write_text(cv, encoding="utf-8")
    (pkg / "cover-letter.md").write_text(cover, encoding="utf-8")


def test_create_snapshots_cv_and_cover_from_disk(
    client_and_store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _ = client_and_store
    out_root = tmp_path / "out"
    out_root.mkdir()
    monkeypatch.setattr(package_module, "OUT_ROOT", out_root)
    _stage_package(out_root, "snap", cv="# CV body", cover="# Cover body")

    body = client.post(
        "/api/applications", json={"slug": "snap", "job_title": "Eng"}
    ).json()
    assert body["cv_markdown"] == "# CV body"
    assert body["cover_letter_markdown"] == "# Cover body"


def test_download_returns_snapshotted_markdown(
    client_and_store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client, _ = client_and_store
    out_root = tmp_path / "out"
    out_root.mkdir()
    monkeypatch.setattr(package_module, "OUT_ROOT", out_root)
    _stage_package(out_root, "dl", cv="# CV body", cover="# Cover body")
    app = client.post(
        "/api/applications", json={"slug": "dl", "job_title": "Eng"}
    ).json()

    cv = client.get(f"/api/applications/{app['id']}/download/cv")
    assert cv.status_code == 200
    assert cv.text == "# CV body"
    assert cv.headers["content-type"].startswith("text/markdown")
    assert "attachment" in cv.headers["content-disposition"]
    assert 'filename="cv.md"' in cv.headers["content-disposition"]

    cover = client.get(f"/api/applications/{app['id']}/download/cover")
    assert cover.status_code == 200
    assert cover.text == "# Cover body"
    assert 'filename="cover-letter.md"' in cover.headers["content-disposition"]


def test_create_without_package_files_stores_none(client_and_store):
    client, _ = client_and_store
    body = client.post(
        "/api/applications", json={"slug": "no-files-xyz", "job_title": "Eng"}
    ).json()
    assert body["cv_markdown"] is None
    assert body["cover_letter_markdown"] is None


def test_download_missing_snapshot_is_404(client_and_store):
    client, _ = client_and_store
    app = client.post(
        "/api/applications", json={"slug": "nofiles", "job_title": "Eng"}
    ).json()
    assert client.get(f"/api/applications/{app['id']}/download/cv").status_code == 404


def test_download_unknown_kind_is_404(client_and_store):
    client, _ = client_and_store
    app = client.post(
        "/api/applications", json={"slug": "k", "job_title": "Eng"}
    ).json()
    assert client.get(f"/api/applications/{app['id']}/download/foo").status_code == 404
