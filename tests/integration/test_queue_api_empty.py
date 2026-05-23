"""GET /api/queue empty-state integration tests (Story 6.3, AC3).

Three flavors of "no packages staged yet": the `./out/` directory exists but
is empty, the `./out/` directory does not exist at all (fresh install), and
`./out/` contains slug directories whose `metadata.json` is missing. All
three must return `{"held_count": 0, "recent": []}` with HTTP 200 — never a
404, never a 500, never a half-populated body.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app


def _stage_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point `PROJECT_ROOT` at *tmp_path* without creating `./out/`."""
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)


def test_get_queue_returns_empty_when_out_root_missing(
    tmp_path, monkeypatch,
) -> None:
    _stage_project_root(tmp_path, monkeypatch)
    # Do NOT create `./out/`.

    client = TestClient(create_app())
    response = client.get("/api/queue")
    assert response.status_code == 200
    assert response.json() == {"held_count": 0, "recent": []}


def test_get_queue_returns_empty_when_out_root_is_empty(
    tmp_path, monkeypatch,
) -> None:
    _stage_project_root(tmp_path, monkeypatch)
    (tmp_path / "out").mkdir()

    client = TestClient(create_app())
    response = client.get("/api/queue")
    assert response.status_code == 200
    assert response.json() == {"held_count": 0, "recent": []}


def test_get_queue_skips_slugs_with_missing_metadata(
    tmp_path, monkeypatch,
) -> None:
    _stage_project_root(tmp_path, monkeypatch)
    out_root = tmp_path / "out"
    # A slug directory with no sidecar — e.g. a partial / aborted run.
    (out_root / "partial-slug").mkdir(parents=True)
    (out_root / "partial-slug" / "cv.md").write_text("# CV\n", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/api/queue")
    assert response.status_code == 200
    assert response.json() == {"held_count": 0, "recent": []}
