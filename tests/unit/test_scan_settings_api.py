# tests/unit/test_scan_settings_api.py
import pytest
from fastapi.testclient import TestClient
from tests.fake_scan_store import FakeScanStore

from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_store


@pytest.fixture
def client():
    app = create_app()
    store = FakeScanStore()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)

def test_get_settings_returns_defaults(client):
    r = client.get("/api/scan/settings")
    assert r.status_code == 200
    assert r.json()["enabled"] is True

def test_put_settings_saves(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": ["Architect"], "sites_enabled": ["linkedin"],
        "picks_per_site": 5, "enabled": False,
    })
    assert r.status_code == 200
    assert r.json()["picks_per_site"] == 5
    assert client.get("/api/scan/settings").json()["enabled"] is False

def test_put_settings_rejects_empty_titles(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": [], "sites_enabled": ["indeed"],
        "picks_per_site": 3, "enabled": True,
    })
    assert r.status_code == 422

def test_put_settings_rejects_unknown_site(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": ["Dev"], "sites_enabled": ["monster"],
        "picks_per_site": 3, "enabled": True,
    })
    assert r.status_code == 422

def test_put_settings_rejects_out_of_range_picks(client):
    r = client.put("/api/scan/settings", json={
        "search_titles": ["Dev"], "sites_enabled": ["linkedin"],
        "picks_per_site": 11, "enabled": True,
    })
    assert r.status_code == 422
