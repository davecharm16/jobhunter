# tests/unit/test_scan_generate_api.py
import pytest
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store, get_tailor
from tests.fake_scan_store import FakeScanStore

class _FakeOutcome:
    def __init__(self, slug): self.slug = slug

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
    app.dependency_overrides[get_tailor] = lambda: (lambda jd_text, url, source: "my-slug")
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 200
    assert r.json() == {"slug": "my-slug", "status": "generated"}
    assert c.get("/api/scan/candidates").json()[0]["status"] == "generated"

def test_generate_failure_leaves_new(client):
    app, store = client
    def _boom(jd_text, url, source): raise RuntimeError("spend cap")
    app.dependency_overrides[get_tailor] = lambda: _boom
    c = _seed(app)
    cid = c.get("/api/scan/candidates").json()[0]["id"]
    r = c.post(f"/api/scan/candidates/{cid}/generate")
    assert r.status_code == 502
    assert c.get("/api/scan/candidates").json()[0]["status"] == "new"

def test_generate_unknown_candidate_404(client):
    app, store = client
    app.dependency_overrides[get_tailor] = lambda: (lambda jd_text, url, source: "s")
    from fastapi.testclient import TestClient
    r = TestClient(app).post("/api/scan/candidates/nope/generate")
    assert r.status_code == 404
