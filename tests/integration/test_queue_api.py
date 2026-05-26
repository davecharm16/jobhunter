"""GET /api/queue integration tests (Story 6.3, AC1).

Mirrors `test_stats_api.py`: synthesizes metadata sidecars under a tmp
`./out/` and monkeypatches `config_module.PROJECT_ROOT` so the queue route
reads from the fixture instead of the repo's real `./out/`. Held packages
live co-located at `./out/<slug>/` (identified by `metadata.held: true`) —
the queue route filters on that flag rather than walking a `./out/_held/`
tree (see `routes/queue.py` docstring for the architectural deviation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app


def _stage_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `PROJECT_ROOT` at *tmp_path* so `./out/` resolves into the fixture."""
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)

    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    return out_root


def _sidecar(
    *,
    slug: str,
    created_at: str = "2026-05-20T00:00:00Z",
    source_board: str = "linkedin",
    drift: dict[str, str] | None = None,
    held: bool = False,
    override_applied: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "slug": slug,
        "jd_source": "paste",
        "artifacts_produced": ["cv", "cover_letter"],
        "cost": {
            "total_usd": "0.010000",
            "per_app_target_usd": "0.250000",
            "exceeded_per_app_target": False,
            "calls": [],
        },
        "created_at": created_at,
        "source_board": source_board,
        "parsed_jd": {},
        "red_flags": [],
        "prompt_templates": {},
        "drift_verdicts": dict(
            drift
            or {
                "fabrication": "pass",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            }
        ),
        "override": {
            "applied": override_applied,
            "reason": "ok" if override_applied else None,
        },
        "error": None,
        "held": held,
        "held_path": None,
    }
    return body


def _write(out_root: Path, payload: dict[str, Any]) -> Path:
    slug_dir = out_root / payload["slug"]
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _snapshot_out_tree(out_root: Path) -> dict[str, str]:
    """Capture path -> content for every file under *out_root* (read-only guard)."""
    snapshot: dict[str, str] = {}
    for path in sorted(out_root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(out_root))] = path.read_text(
                encoding="utf-8"
            )
    return snapshot


# --- AC1: shape + held_count + sort order ---------------------------------


def test_get_queue_returns_held_count_and_recent_shape(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(slug="passed-1", created_at="2026-05-20T10:00:00Z"),
    )
    _write(
        out_root,
        _sidecar(
            slug="held-fab",
            created_at="2026-05-20T11:00:00Z",
            held=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    response = client.get("/api/queue")
    assert response.status_code == 200
    body = response.json()

    assert body["held_count"] == 1
    assert isinstance(body["recent"], list)
    assert len(body["recent"]) == 2
    # Each entry has the four projection keys and nothing else.
    for entry in body["recent"]:
        assert set(entry.keys()) == {
            "slug",
            "source_board",
            "verdict",
            "timestamp",
        }


def test_get_queue_sorts_recent_descending_by_created_at(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(slug="older", created_at="2026-05-18T09:00:00Z"),
    )
    _write(
        out_root,
        _sidecar(slug="newest", created_at="2026-05-20T15:00:00Z"),
    )
    _write(
        out_root,
        _sidecar(slug="middle", created_at="2026-05-19T12:00:00Z"),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    slugs = [entry["slug"] for entry in body["recent"]]
    assert slugs == ["newest", "middle", "older"]


def test_get_queue_caps_recent_at_ten_entries(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    for index in range(15):
        _write(
            out_root,
            _sidecar(
                slug=f"slug-{index:02d}",
                created_at=f"2026-05-{index + 1:02d}T00:00:00Z",
            ),
        )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert len(body["recent"]) == 10
    # Most recent ten should be slug-14 ... slug-05 (descending).
    assert body["recent"][0]["slug"] == "slug-14"
    assert body["recent"][-1]["slug"] == "slug-05"


# --- AC1: verdict mapping -------------------------------------------------


def test_get_queue_verdict_pass_when_not_held(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="clean"))

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["recent"][0]["verdict"] == "pass"


def test_get_queue_verdict_overridden_when_release_recorded(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="released",
            held=False,
            override_applied=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["recent"][0]["verdict"] == "overridden"


def test_get_queue_verdict_held_fabrication_single_fail(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="fab",
            held=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["recent"][0]["verdict"] == "held:fabrication"


def test_get_queue_verdict_held_content_loss(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="loss",
            held=True,
            drift={
                "fabrication": "pass",
                "content_loss": "fail",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["recent"][0]["verdict"] == "held:content-loss"


def test_get_queue_verdict_held_keyword_stuffing(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="kw",
            held=True,
            drift={
                "fabrication": "pass",
                "content_loss": "pass",
                "keyword_stuffing": "fail",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["recent"][0]["verdict"] == "held:keyword-stuffing"


def test_get_queue_verdict_held_multiple_when_two_fails(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="combo",
            held=True,
            drift={
                "fabrication": "fail",
                "content_loss": "fail",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["recent"][0]["verdict"] == "held:multiple"


# --- AC1: mixed corpus + held_count counts only held ---------------------


def test_get_queue_held_count_only_counts_held_flag(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="pass-1"))
    _write(out_root, _sidecar(slug="pass-2"))
    _write(
        out_root,
        _sidecar(
            slug="held-1",
            held=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )
    _write(
        out_root,
        _sidecar(
            slug="held-2",
            held=True,
            drift={
                "fabrication": "pass",
                "content_loss": "fail",
                "keyword_stuffing": "pass",
            },
        ),
    )
    # Overridden: held=False but had drift fails — should NOT count.
    _write(
        out_root,
        _sidecar(
            slug="overridden",
            held=False,
            override_applied=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    assert body["held_count"] == 2


def test_get_queue_carries_source_board_and_timestamp(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="upwork-slug",
            source_board="upwork",
            created_at="2026-05-20T10:30:00Z",
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    entry = body["recent"][0]
    assert entry["slug"] == "upwork-slug"
    assert entry["source_board"] == "upwork"
    assert entry["timestamp"] == "2026-05-20T10:30:00Z"


# --- AC1: read-only invariant --------------------------------------------


def test_get_queue_does_not_mutate_out_tree(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="pass-1"))
    _write(
        out_root,
        _sidecar(
            slug="held-1",
            held=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )
    # Drop a non-sidecar artifact alongside; the route must not touch it.
    (out_root / "held-1" / "cv.md").write_text("# CV\n", encoding="utf-8")

    before = _snapshot_out_tree(out_root)

    client = TestClient(create_app())
    response = client.get("/api/queue")
    assert response.status_code == 200

    after = _snapshot_out_tree(out_root)
    assert before == after


# --- Story 8.1: overridden packages in queue --------------------------------


def test_get_queue_includes_overridden_packages_in_recent(
    tmp_path, monkeypatch,
) -> None:
    """Packages under ``_overridden/`` appear in the recent list."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(slug="normal-pass", created_at="2026-05-20T10:00:00Z"),
    )
    # Write an overridden package under _overridden/
    overridden_root = out_root / "_overridden"
    overridden_root.mkdir()
    _write(
        overridden_root,
        _sidecar(
            slug="approved-pkg",
            created_at="2026-05-20T12:00:00Z",
            override_applied=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()

    slugs = [entry["slug"] for entry in body["recent"]]
    assert "approved-pkg" in slugs
    assert "normal-pass" in slugs
    assert len(body["recent"]) == 2


def test_get_queue_overridden_package_verdict_is_overridden(
    tmp_path, monkeypatch,
) -> None:
    """Overridden packages from ``_overridden/`` render verdict ``overridden``."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    overridden_root = out_root / "_overridden"
    overridden_root.mkdir()
    _write(
        overridden_root,
        _sidecar(
            slug="released",
            created_at="2026-05-20T14:00:00Z",
            held=False,
            override_applied=True,
            drift={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()

    assert len(body["recent"]) == 1
    assert body["recent"][0]["verdict"] == "overridden"
    assert body["recent"][0]["slug"] == "released"


def test_get_queue_overridden_packages_sort_with_normal(
    tmp_path, monkeypatch,
) -> None:
    """Overridden packages are interleaved correctly by timestamp."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(slug="oldest", created_at="2026-05-18T09:00:00Z"),
    )
    _write(
        out_root,
        _sidecar(slug="newest", created_at="2026-05-22T15:00:00Z"),
    )
    overridden_root = out_root / "_overridden"
    overridden_root.mkdir()
    _write(
        overridden_root,
        _sidecar(
            slug="middle-overridden",
            created_at="2026-05-20T12:00:00Z",
            override_applied=True,
        ),
    )

    client = TestClient(create_app())
    body = client.get("/api/queue").json()
    slugs = [entry["slug"] for entry in body["recent"]]
    assert slugs == ["newest", "middle-overridden", "oldest"]
