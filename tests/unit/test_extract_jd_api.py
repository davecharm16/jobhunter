"""Tests for POST /api/extract-jd — screenshot → JD text (vision via n8n)."""

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_jd_extractor


@pytest.fixture
def app():
    return create_app()


def test_extract_jd_success(app):
    app.dependency_overrides[get_jd_extractor] = lambda: (
        lambda image_b64, content_type: "Senior Solutions Architect — remote. Required: ..."
    )
    r = TestClient(app).post(
        "/api/extract-jd", json={"image_b64": "aW1n", "content_type": "image/png"}
    )
    assert r.status_code == 200
    assert r.json()["jd_text"].startswith("Senior Solutions Architect")


def test_extract_jd_vision_failure_502(app):
    def _boom(image_b64, content_type):
        raise RuntimeError("vision unreachable")

    app.dependency_overrides[get_jd_extractor] = lambda: _boom
    r = TestClient(app).post("/api/extract-jd", json={"image_b64": "aW1n"})
    assert r.status_code == 502


def test_extract_jd_empty_result_422(app):
    app.dependency_overrides[get_jd_extractor] = lambda: (
        lambda image_b64, content_type: "   "
    )
    r = TestClient(app).post("/api/extract-jd", json={"image_b64": "aW1n"})
    assert r.status_code == 422


def test_extract_jd_missing_image_422(app):
    # empty image_b64 fails pydantic min_length validation
    r = TestClient(app).post("/api/extract-jd", json={"image_b64": ""})
    assert r.status_code == 422
