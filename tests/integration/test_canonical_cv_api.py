"""GET/PUT /api/canonical-cv tests (Story 2.13).

The reader contract from DECISIONS.md §2 says `read_canonical_cv()` is the
single entry point; the route handlers delegate to it on every request, so the
tests stage a per-test canonical-cv file via the `_web_helpers` fixture and
exercise the FastAPI app in-process via `TestClient`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
from tests.integration._web_helpers import stage_canonical_cv

from jobhunter.web.api import create_app


def _load_cv(cv_path: Path) -> dict:
    return json.loads(cv_path.read_text(encoding="utf-8"))


# --- AC1: GET --------------------------------------------------------------


def test_get_canonical_cv_returns_full_document(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/canonical-cv")

    assert response.status_code == 200
    body = response.json()
    on_disk = _load_cv(cv_path)
    assert body == on_disk


def test_get_canonical_cv_preserves_tags_and_high_impact(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    doc = _load_cv(cv_path)
    doc["work"][0]["tags"] = ["python", "fastapi"]
    doc["work"][0]["highImpact"] = True
    doc["skills"][0]["tags"] = ["backend"]
    doc["skills"][0]["highImpact"] = True
    cv_path.write_text(json.dumps(doc), encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/api/canonical-cv")

    assert response.status_code == 200
    body = response.json()
    assert body["work"][0]["tags"] == ["python", "fastapi"]
    assert body["work"][0]["highImpact"] is True
    assert body["skills"][0]["tags"] == ["backend"]
    assert body["skills"][0]["highImpact"] is True


def test_get_canonical_cv_returns_404_when_file_missing(
    missing_canonical_cv: Path,
) -> None:
    client = TestClient(create_app())
    response = client.get("/api/canonical-cv")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_canonical_cv_returns_500_for_pdf_path(
    nonexistent_pdf_canonical_cv: Path,
) -> None:
    client = TestClient(create_app())
    response = client.get("/api/canonical-cv")

    assert response.status_code == 500
    assert "pdf" in response.json()["detail"].lower()


def test_get_canonical_cv_returns_500_with_json_pointer_when_malformed(
    tmp_path, monkeypatch,
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    doc = _load_cv(cv_path)
    # `basics.email` must be a valid email per JSON Resume schema.
    doc["basics"]["email"] = "not-an-email"
    cv_path.write_text(json.dumps(doc), encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/api/canonical-cv")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "/basics/email" in detail


# --- AC3: PUT --------------------------------------------------------------


def test_put_canonical_cv_writes_document_and_returns_path(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original = _load_cv(cv_path)
    updated = copy.deepcopy(original)
    updated["basics"]["label"] = "Senior Backend Engineer"

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv", json=updated)

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is True
    assert body["path"].endswith("canonical-cv.json")

    on_disk = _load_cv(cv_path)
    assert on_disk["basics"]["label"] == "Senior Backend Engineer"


def test_put_canonical_cv_round_trips_tags_and_high_impact(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    doc = _load_cv(cv_path)
    doc["work"][0]["tags"] = ["python", "n8n"]
    doc["work"][0]["highImpact"] = True
    doc["projects"][0]["tags"] = ["llm"]
    doc["projects"][0]["highImpact"] = False
    doc["skills"][0]["tags"] = ["backend"]
    doc["skills"][0]["highImpact"] = True

    client = TestClient(create_app())
    put_response = client.put("/api/canonical-cv", json=doc)
    assert put_response.status_code == 200

    get_response = client.get("/api/canonical-cv")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["work"][0]["tags"] == ["python", "n8n"]
    assert body["work"][0]["highImpact"] is True
    assert body["projects"][0]["tags"] == ["llm"]
    assert body["projects"][0]["highImpact"] is False
    assert body["skills"][0]["tags"] == ["backend"]
    assert body["skills"][0]["highImpact"] is True

    on_disk = _load_cv(cv_path)
    assert on_disk["work"][0]["tags"] == ["python", "n8n"]
    assert on_disk["work"][0]["highImpact"] is True


def test_put_canonical_cv_full_round_trip_preserves_all_fields(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original = _load_cv(cv_path)

    client = TestClient(create_app())
    get_response = client.get("/api/canonical-cv")
    assert get_response.status_code == 200
    fetched = get_response.json()

    put_response = client.put("/api/canonical-cv", json=fetched)
    assert put_response.status_code == 200

    on_disk = _load_cv(cv_path)
    assert on_disk == original


def test_put_canonical_cv_invalid_payload_returns_422_and_does_not_write(
    tmp_path, monkeypatch,
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original_bytes = cv_path.read_bytes()

    bad = _load_cv(cv_path)
    bad["basics"]["email"] = "not-an-email"

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv", json=bad)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "schema_validation_failed"
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 1
    paths = [err["path"] for err in body["errors"]]
    assert any("/basics/email" in p for p in paths)

    # File on disk MUST be unchanged.
    assert cv_path.read_bytes() == original_bytes


def test_put_canonical_cv_invalid_tag_type_returns_422(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original_bytes = cv_path.read_bytes()

    bad = _load_cv(cv_path)
    # `tags` must be an array of strings.
    bad["work"][0]["tags"] = [123, 456]

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv", json=bad)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "schema_validation_failed"
    paths = [err["path"] for err in body["errors"]]
    assert any(p.startswith("/work/0/tags") for p in paths)
    assert cv_path.read_bytes() == original_bytes


def test_put_canonical_cv_invalid_high_impact_type_returns_422(
    tmp_path, monkeypatch,
) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    original_bytes = cv_path.read_bytes()

    bad = _load_cv(cv_path)
    bad["work"][0]["highImpact"] = "yes"  # must be bool

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv", json=bad)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "schema_validation_failed"
    paths = [err["path"] for err in body["errors"]]
    assert any(p.startswith("/work/0/highImpact") for p in paths)
    assert cv_path.read_bytes() == original_bytes


def test_put_canonical_cv_leaves_no_tmp_file_after_success(tmp_path, monkeypatch) -> None:
    cv_path = stage_canonical_cv(tmp_path, monkeypatch)
    doc = _load_cv(cv_path)
    doc["basics"]["label"] = "Updated"

    client = TestClient(create_app())
    response = client.put("/api/canonical-cv", json=doc)
    assert response.status_code == 200

    tmp_sibling = cv_path.with_suffix(cv_path.suffix + ".tmp")
    assert not tmp_sibling.exists()
