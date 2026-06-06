"""GET /api/canonical-cv/raw and PUT /api/canonical-cv/raw tests (Story 02-1).

Raw-text round-trip for the canonical CV: the user can read the file as plain
text, edit it, and PUT it back. Validation reuses the same JSON Resume schema
path as the existing structured endpoint, so invalid JSON / invalid schema →
422, file unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from tests.integration._web_helpers import stage_canonical_cv


def _load_cv(cv_path: Path) -> dict:
    return json.loads(cv_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# GET /api/canonical-cv/raw
# ---------------------------------------------------------------------------


def test_get_canonical_cv_raw_returns_content_string(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/canonical-cv/raw")

    assert response.status_code == 200
    body = response.json()
    assert "content" in body
    assert isinstance(body["content"], str)
    # The content must be the exact on-disk text.
    assert body["content"] == cv_path.read_text(encoding="utf-8")


def test_get_canonical_cv_raw_returns_404_when_file_missing(
    tmp_path, monkeypatch
) -> None:
    # Point CANONICAL_CV_PATH at a path that does not exist.
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    missing = tmp_path / "canonical-cv.json"
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", missing)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", missing)

    client = TestClient(create_app())
    response = client.get("/api/canonical-cv/raw")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_canonical_cv_raw_content_is_valid_json(tmp_path, monkeypatch) -> None:
    stage_canonical_cv(tmp_path, monkeypatch)

    client = TestClient(create_app())
    body = client.get("/api/canonical-cv/raw").json()

    # The raw text must itself be parseable as JSON.
    parsed = json.loads(body["content"])
    assert isinstance(parsed, dict)
    assert "basics" in parsed


# ---------------------------------------------------------------------------
# PUT /api/canonical-cv/raw — valid payload
# ---------------------------------------------------------------------------


def test_put_canonical_cv_raw_writes_and_returns_200(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original = _load_cv(cv_path)
    original["basics"]["label"] = "Raw Edit Label"
    new_text = json.dumps(original, indent=2) + "\n"

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv/raw", json={"content": new_text})

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is True
    # File on disk must reflect the change.
    on_disk = _load_cv(cv_path)
    assert on_disk["basics"]["label"] == "Raw Edit Label"


def test_put_canonical_cv_raw_leaves_no_tmp_file_after_success(
    tmp_path, monkeypatch
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    doc = _load_cv(cv_path)
    doc["basics"]["label"] = "No Tmp File"
    new_text = json.dumps(doc)

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv/raw", json={"content": new_text})
    assert response.status_code == 200

    tmp_sibling = cv_path.with_suffix(cv_path.suffix + ".tmp")
    assert not tmp_sibling.exists()


def test_put_canonical_cv_raw_round_trips_tags_and_high_impact(
    tmp_path, monkeypatch
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    doc = _load_cv(cv_path)
    doc["work"][0]["tags"] = ["python", "raw-edit"]
    doc["work"][0]["highImpact"] = True

    client = TestClient(create_app())
    put_resp = client.put(
        "/api/canonical-cv/raw", json={"content": json.dumps(doc)}
    )
    assert put_resp.status_code == 200

    get_resp = client.get("/api/canonical-cv/raw")
    assert get_resp.status_code == 200
    parsed = json.loads(get_resp.json()["content"])
    assert parsed["work"][0]["tags"] == ["python", "raw-edit"]
    assert parsed["work"][0]["highImpact"] is True


# ---------------------------------------------------------------------------
# PUT /api/canonical-cv/raw — invalid payloads
# ---------------------------------------------------------------------------


def test_put_canonical_cv_raw_invalid_json_returns_422_file_unchanged(
    tmp_path, monkeypatch
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original_bytes = cv_path.read_bytes()

    client = TestClient(create_app())
    response = client.put(
        "/api/canonical-cv/raw", json={"content": "{ this is not valid JSON {{"}
    )

    assert response.status_code == 422
    body = response.json()
    assert "json" in body["detail"].lower() or "parse" in body["detail"].lower()
    # File MUST be unchanged.
    assert cv_path.read_bytes() == original_bytes


def test_put_canonical_cv_raw_schema_violation_returns_422_file_unchanged(
    tmp_path, monkeypatch
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original_bytes = cv_path.read_bytes()

    bad = _load_cv(cv_path)
    bad["basics"]["email"] = "not-an-email"

    client = TestClient(create_app())
    response = client.put(
        "/api/canonical-cv/raw", json={"content": json.dumps(bad)}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "schema_validation_failed"
    assert isinstance(body["errors"], list)
    assert any("/basics/email" in e["path"] for e in body["errors"])
    # File MUST be unchanged.
    assert cv_path.read_bytes() == original_bytes


def test_put_canonical_cv_raw_missing_content_key_returns_422(
    tmp_path, monkeypatch
) -> None:
    stage_canonical_cv(tmp_path, monkeypatch)

    client = TestClient(create_app())
    # No "content" key at all — should be rejected by FastAPI/Pydantic.
    response = client.put("/api/canonical-cv/raw", json={"wrong_key": "..."})

    assert response.status_code == 422
