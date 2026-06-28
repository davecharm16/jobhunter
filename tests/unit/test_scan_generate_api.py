# tests/unit/test_scan_generate_api.py
import pytest
from fastapi.testclient import TestClient
from tests.fake_scan_store import FakeScanStore

from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store, get_tailor


@pytest.fixture
def store():
    return FakeScanStore()

@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return app, store

def _seed(app):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    c.post("/api/scan/results", json={"site_summary": {}, "candidates": [{
        "site": "indeed", "url": "https://jobs.example.com/1", "title": "Dev",
        "company": "Acme", "location": "Remote", "jd_text": "JD body",
        "fit_reason": "x", "fit_score": 0.5}]})
    return c

def test_generate_success_sets_generated_and_slug(client):
    app, store = client
    app.dependency_overrides[get_tailor] = lambda: (
        lambda jd_text, url, source, title: "my-slug"
    )
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 200
    assert r.json() == {"slug": "my-slug", "status": "generated"}
    assert c.get("/api/scan/candidates").json()[0]["status"] == "generated"

def test_generate_passes_candidate_title_as_job_title(client):
    app, store = client
    seen: dict[str, str] = {}

    def _capture(jd_text, url, source, title):
        seen["title"] = title
        return "slug-x"

    app.dependency_overrides[get_tailor] = lambda: _capture
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 200
    # The candidate's scraped title ("Dev") is what the tailor (and thus the
    # package job_title) receives — not a parsed salary line.
    assert seen["title"] == "Dev"

def test_generate_failure_leaves_new(client):
    app, store = client
    def _boom(jd_text, url, source, title): raise RuntimeError("spend cap")
    app.dependency_overrides[get_tailor] = lambda: _boom
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 502
    assert c.get("/api/scan/candidates").json()[0]["status"] == "new"

def test_generate_unknown_candidate_404(client):
    app, store = client
    app.dependency_overrides[get_tailor] = lambda: (
        lambda jd_text, url, source, title: "s"
    )
    r = TestClient(app).post("/api/scan/candidates/nope/generate")
    assert r.status_code == 404
