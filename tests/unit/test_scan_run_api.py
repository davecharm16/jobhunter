"""Tests for POST /api/scan/run — the manual 'Run scan now' trigger."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tests.fake_scan_store import FakeScanStore

from jobhunter.web.api import create_app
from jobhunter.web.routes import scan as scan_routes
from jobhunter.web.routes.scan import get_scan_trigger, get_store


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_store] = lambda: FakeScanStore()
    return app


def test_run_returns_503_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(
        scan_routes,
        "load_runtime_config",
        lambda: SimpleNamespace(n8n_scan_trigger_url=None),
    )
    r = TestClient(client).post("/api/scan/run")
    assert r.status_code == 503


def test_run_triggers_when_configured(client, monkeypatch):
    monkeypatch.setattr(
        scan_routes,
        "load_runtime_config",
        lambda: SimpleNamespace(n8n_scan_trigger_url="http://n8n.example/webhook/scan"),
    )
    called = {}
    client.dependency_overrides[get_scan_trigger] = lambda: (
        lambda url: called.setdefault("url", url)
    )
    r = TestClient(client).post("/api/scan/run")
    assert r.status_code == 200
    assert r.json() == {"triggered": True}
    assert called["url"] == "http://n8n.example/webhook/scan"


def test_run_returns_502_when_engine_unreachable(client, monkeypatch):
    monkeypatch.setattr(
        scan_routes,
        "load_runtime_config",
        lambda: SimpleNamespace(n8n_scan_trigger_url="http://n8n.example/webhook/scan"),
    )

    def _boom(url):
        raise RuntimeError("connection refused")

    client.dependency_overrides[get_scan_trigger] = lambda: _boom
    r = TestClient(client).post("/api/scan/run")
    assert r.status_code == 502
