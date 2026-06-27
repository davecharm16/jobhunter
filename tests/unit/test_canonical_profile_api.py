from fastapi.testclient import TestClient

from jobhunter.web.api import create_app


def test_canonical_profile_endpoint_returns_projection(monkeypatch):
    import jobhunter.web.routes.scan as scan_routes
    monkeypatch.setattr(
        scan_routes, "read_canonical_cv",
        lambda: {"basics": {"name": "Dave", "label": "SD", "summary": "s"},
                 "skills": [{"name": "Mobile"}], "work": []},
    )
    client = TestClient(create_app())  # TestClient is loopback -> token bypassed
    r = client.get("/api/canonical-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Dave"
    assert body["skills"] == ["Mobile"]
