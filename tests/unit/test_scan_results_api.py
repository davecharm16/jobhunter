# tests/unit/test_scan_results_api.py
import pytest
from fastapi.testclient import TestClient
from tests.fake_scan_store import FakeScanStore

from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store


@pytest.fixture
def store():
    return FakeScanStore()

@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)

def _payload(url="https://jobs.example.com/1"):
    return {
        "started_at": "2026-06-26T01:00:00Z",
        "finished_at": "2026-06-26T01:05:00Z",
        "site_summary": {"indeed": {"status": "ok", "count": 1}},
        "candidates": [{
            "site": "indeed", "url": url, "title": "Dev", "company": "Acme",
            "location": "Remote", "jd_text": "Full JD body",
            "fit_reason": "fits", "fit_score": 0.8,
        }],
    }

def test_results_inserts_new(client):
    r = client.post("/api/scan/results", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == 1 and body["new"] == 1 and body["skipped"] == 0

def test_results_is_idempotent(client):
    client.post("/api/scan/results", json=_payload())
    r = client.post("/api/scan/results", json=_payload())
    assert r.json()["new"] == 0 and r.json()["skipped"] == 1

def test_results_rejects_unknown_site(client):
    bad = _payload()
    bad["candidates"][0]["site"] = "monster"
    r = client.post("/api/scan/results", json=bad)
    assert r.status_code == 422

def test_known_urls(client):
    client.post("/api/scan/results", json=_payload())
    r = client.get("/api/scan/known-urls")
    assert r.status_code == 200
    assert r.json()["urls"] == ["https://jobs.example.com/1"]

def test_results_mixed_new_and_known(client):
    # Post a candidate with a known URL first
    client.post("/api/scan/results", json=_payload("https://jobs.example.com/known"))
    # Now post a batch with one known and one fresh URL
    multi = {
        "started_at": "2026-06-26T01:00:00Z",
        "finished_at": "2026-06-26T01:05:00Z",
        "site_summary": {},
        "candidates": [
            {"site": "indeed", "url": "https://jobs.example.com/known", "title": "Dev",
             "company": "A", "location": "Remote", "jd_text": "x", "fit_reason": "y", "fit_score": 0.5},
            {"site": "linkedin", "url": "https://jobs.example.com/fresh", "title": "Dev2",
             "company": "B", "location": "Remote", "jd_text": "x", "fit_reason": "y", "fit_score": 0.6},
        ],
    }
    r = client.post("/api/scan/results", json=multi)
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == 2 and body["new"] == 1 and body["skipped"] == 1
