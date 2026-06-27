# tests/unit/test_scan_results_api.py
from types import SimpleNamespace

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

def test_results_drops_incomplete_instead_of_422(client):
    # one good candidate + one missing jd_text → batch accepted, bad one dropped
    payload = _payload()
    payload["candidates"].append({
        "site": "indeed", "url": "https://jobs.example.com/2", "title": "Dev2",
        "jd_text": "", "company": None, "location": None,
    })
    r = client.post("/api/scan/results", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == 2
    assert body["ingested"] == 1
    assert body["dropped_incomplete"] == 1
    assert body["new"] == 1

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

def test_zero_new_sends_no_notification(client):
    # First POST inserts the candidate (new=1)
    client.post("/api/scan/results", json=_payload())
    # Re-POST the same candidate: new=0, no notification attempted; must still be 200
    r = client.post("/api/scan/results", json=_payload())
    assert r.status_code == 200
    assert r.json()["new"] == 0

def test_notify_failure_does_not_fail_ingest(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("notify boom")

    # Monkeypatch notify_scan to raise so we can verify ingest still succeeds
    monkeypatch.setattr("jobhunter.web.routes.scan.notify_scan", _boom)
    # Monkeypatch load_runtime_config to expose a truthy webhook so notify path is entered
    monkeypatch.setattr(
        "jobhunter.web.routes.scan.load_runtime_config",
        lambda: SimpleNamespace(gchat_webhook_url="http://x"),
    )
    # A fresh URL ensures new > 0, which triggers the notify path
    r = client.post("/api/scan/results", json=_payload("https://jobs.example.com/notify-test"))
    assert r.status_code == 200
    assert r.json()["new"] == 1

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
