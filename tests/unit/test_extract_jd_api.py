"""Tests for POST /api/extract-jd — screenshot(s) → JD text (vision via n8n)."""

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from jobhunter.web.routes.scan import get_jd_extractor


@pytest.fixture
def app():
    return create_app()


def test_extract_jd_single_image(app):
    app.dependency_overrides[get_jd_extractor] = lambda: (
        lambda image_b64, content_type: "Senior Solutions Architect — remote."
    )
    r = TestClient(app).post(
        "/api/extract-jd",
        json={"images": [{"image_b64": "aW1n", "content_type": "image/png"}]},
    )
    assert r.status_code == 200
    assert r.json()["jd_text"].startswith("Senior Solutions Architect")


def test_extract_jd_multiple_images_concatenated(app):
    # each image yields its own fragment; output is them joined in order
    parts = iter(["PART ONE responsibilities", "PART TWO requirements"])
    app.dependency_overrides[get_jd_extractor] = lambda: (
        lambda image_b64, content_type: next(parts)
    )
    r = TestClient(app).post(
        "/api/extract-jd",
        json={"images": [{"image_b64": "aW1n1"}, {"image_b64": "aW1n2"}]},
    )
    assert r.status_code == 200
    body = r.json()["jd_text"]
    assert "PART ONE" in body and "PART TWO" in body
    assert body.index("PART ONE") < body.index("PART TWO")


def test_extract_jd_vision_failure_502(app):
    def _boom(image_b64, content_type):
        raise RuntimeError("vision unreachable")

    app.dependency_overrides[get_jd_extractor] = lambda: _boom
    r = TestClient(app).post(
        "/api/extract-jd", json={"images": [{"image_b64": "aW1n"}]}
    )
    assert r.status_code == 502


def test_extract_jd_all_empty_422(app):
    app.dependency_overrides[get_jd_extractor] = lambda: (
        lambda image_b64, content_type: "   "
    )
    r = TestClient(app).post(
        "/api/extract-jd", json={"images": [{"image_b64": "aW1n"}]}
    )
    assert r.status_code == 422


def test_extract_jd_no_images_422(app):
    r = TestClient(app).post("/api/extract-jd", json={"images": []})
    assert r.status_code == 422
