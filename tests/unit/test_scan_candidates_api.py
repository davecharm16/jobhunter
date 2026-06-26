# tests/unit/test_scan_candidates_api.py
import pytest
from fastapi.testclient import TestClient
from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store
from tests.fake_scan_store import FakeScanStore

@pytest.fixture
def store():
    return FakeScanStore()

@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)

def _seed(client, url="https://jobs.example.com/1"):
    client.post("/api/scan/results", json={
        "site_summary": {}, "candidates": [{
            "site": "indeed", "url": url, "title": "Dev", "company": "Acme",
            "location": "Remote", "jd_text": "JD", "fit_reason": "x",
            "fit_score": 0.5}]})

def test_list_candidates_filters_status(client):
    _seed(client)
    r = client.get("/api/scan/candidates?status=new")
    assert r.status_code == 200 and len(r.json()) == 1

def test_dismiss_candidate(client):
    _seed(client)
    cid = client.get("/api/scan/candidates").json()[0]["id"]
    r = client.patch(f"/api/scan/candidates/{cid}", json={"status": "dismissed"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"

def test_dismiss_unknown_404(client):
    r = client.patch("/api/scan/candidates/nope", json={"status": "dismissed"})
    assert r.status_code == 404

def test_patch_invalid_status_422(client):
    _seed(client)
    cid = client.get("/api/scan/candidates").json()[0]["id"]
    r = client.patch(f"/api/scan/candidates/{cid}", json={"status": "archived"})
    assert r.status_code == 422

def test_list_scans(client):
    _seed(client)
    r = client.get("/api/scan/scans")
    assert r.status_code == 200 and len(r.json()) == 1
