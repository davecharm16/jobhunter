"""POST /api/override/<slug> integration tests (Story 6.4, AC1-AC5).

Mirrors `test_queue_api.py`: synthesizes a co-located held package under a
per-test tmp `./out/` and monkeypatches `jobhunter.config.PROJECT_ROOT` so
the override route resolves into the fixture instead of the repo's real
`./out/`. The route reads the project root fresh per call (see
`routes/override._resolve_out_root`), so the patch applied here propagates
on every request inside the test.

Architectural deviation note: held packages live co-located at
`./out/<slug>/` (identified by `metadata.held: true`), NOT under a separate
`./out/_held/` tree. Stories 3.4 / 4.2 / 5.3 / 6.2 / 6.3 settled the
co-located layout; Story 6.4 inherits it. After a successful override the
package moves to `./out/_overridden/<slug>/` and `metadata.held` flips to
`false`.

AC4 (no outbound submission) is tested two ways:

1. A unit-import test (`tests/unit/test_override_imports.py`) statically
   pins that the route module imports no notifier / HTTP client.
2. The integration test below mocks `jobhunter.notifier.notify` and
   asserts it is never called during an override request.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app

# ----------------------------- fixtures ----------------------------------


def _stage_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `PROJECT_ROOT` at *tmp_path* so `./out/` resolves into the fixture."""
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)

    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    return out_root


def _held_sidecar(
    *,
    slug: str,
    created_at: str = "2026-05-20T11:00:00Z",
    source_board: str = "linkedin",
    drift: dict[str, str] | None = None,
    held: bool = True,
    override_applied: bool = False,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "jd_source": "paste",
        "artifacts_produced": ["cv.md", "cover-letter.md"],
        "cost": {
            "total_usd": "0.010000",
            "per_app_target_usd": "0.250000",
            "exceeded_per_app_target": False,
            "calls": [],
        },
        "created_at": created_at,
        "source_board": source_board,
        "parsed_jd": {"must_haves": ["Python"]},
        "red_flags": [],
        "prompt_templates": {"tailoring": "v1"},
        "drift_verdicts": dict(
            drift
            or {
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            }
        ),
        "override": {
            "applied": override_applied,
            "reason": "prior" if override_applied else None,
        },
        "error": None,
        "held": held,
        "held_path": None,
    }


def _stage_held_package(
    out_root: Path,
    slug: str,
    *,
    sidecar: dict[str, Any] | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Materialise a held package at `out_root/<slug>/` with sidecar + artifacts."""
    package_dir = out_root / slug
    package_dir.mkdir(parents=True, exist_ok=True)
    payload = sidecar if sidecar is not None else _held_sidecar(slug=slug)
    (package_dir / "metadata.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    files = extra_files or {
        "cv.md": "# Tailored CV\n",
        "cover-letter.md": "# Cover Letter\n",
        "package.drift.json": json.dumps({"fabrication_check": {"verdict": "fail"}}),
    }
    for name, contents in files.items():
        (package_dir / name).write_text(contents, encoding="utf-8")
    return package_dir


# ----------------------------- AC1 + AC2: 422 -----------------------------


def test_override_422_when_body_is_empty(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post("/api/override/acme-slug", json={})

    assert response.status_code == 422
    body = response.json()
    # Pydantic-style detail list naming the missing fields.
    locs = {tuple(error["loc"]) for error in body["detail"]}
    assert ("body", "reason") in locs
    assert ("body", "ack_drift") in locs
    # Package not moved.
    assert (out_root / "acme-slug" / "metadata.json").is_file()
    assert not (out_root / "_overridden" / "acme-slug").exists()


def test_override_422_when_reason_missing(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/acme-slug", json={"ack_drift": True}
    )

    assert response.status_code == 422
    locs = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "reason") in locs


def test_override_422_when_ack_drift_missing(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/acme-slug", json={"reason": "looks fine"}
    )

    assert response.status_code == 422
    locs = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "ack_drift") in locs


def test_override_422_when_reason_is_empty_string(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/acme-slug",
        json={"reason": "", "ack_drift": True},
    )

    assert response.status_code == 422
    body = response.json()
    locs = {tuple(error["loc"]) for error in body["detail"]}
    assert ("body", "reason") in locs


def test_override_422_when_reason_is_whitespace_only(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/acme-slug",
        json={"reason": "   \t\n  ", "ack_drift": True},
    )

    assert response.status_code == 422
    locs = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "reason") in locs


def test_override_422_when_ack_drift_is_string(tmp_path, monkeypatch) -> None:
    """AC2: `ack_drift` must be a strict JSON boolean — no string coercion."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/acme-slug",
        json={"reason": "valid reason", "ack_drift": "maybe"},
    )

    assert response.status_code == 422
    locs = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "ack_drift") in locs


def test_override_422_when_ack_drift_is_integer(tmp_path, monkeypatch) -> None:
    """`StrictBool` rejects integer 1 / 0 coercion as well."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/acme-slug",
        json={"reason": "valid", "ack_drift": 1},
    )

    assert response.status_code == 422
    locs = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "ack_drift") in locs


def test_override_422_response_does_not_mutate_out_tree(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "acme-slug")

    snapshot_before = _snapshot(out_root)

    client = TestClient(create_app())
    response = client.post("/api/override/acme-slug", json={})
    assert response.status_code == 422

    assert _snapshot(out_root) == snapshot_before


# ----------------------------- AC3: success path -------------------------


def test_override_200_moves_package_and_stamps_metadata(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    slug = "acme-senior-backend-2026-05-19"
    _stage_held_package(out_root, slug)

    client = TestClient(create_app())
    response = client.post(
        f"/api/override/{slug}",
        json={
            "reason": "drift was on adjacent-tool phrasing I actually know",
            "ack_drift": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == slug
    assert body["overridden"] is True
    assert body["moved_to"] == f"./out/_overridden/{slug}/"
    assert "submit" in body["note"].lower()

    # Original held directory is gone, overridden directory exists with artifacts.
    assert not (out_root / slug).exists()
    overridden_dir = out_root / "_overridden" / slug
    assert overridden_dir.is_dir()
    assert (overridden_dir / "cv.md").read_text(encoding="utf-8") == "# Tailored CV\n"
    assert (overridden_dir / "cover-letter.md").read_text(encoding="utf-8") == (
        "# Cover Letter\n"
    )

    # Sidecar inside the moved package has the structured override block.
    metadata = json.loads(
        (overridden_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["held"] is False
    override = metadata["override"]
    assert override["applied"] is True
    assert (
        override["reason"]
        == "drift was on adjacent-tool phrasing I actually know"
    )
    assert override["ack_drift"] is True
    # ISO 8601 with trailing Z (matches `metadata.now_iso8601_utc` contract).
    assert override["timestamp"].endswith("Z")
    assert "T" in override["timestamp"]


def test_override_200_preserves_other_metadata_fields(
    tmp_path, monkeypatch,
) -> None:
    """A successful override must not clobber unrelated metadata fields."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    sidecar = _held_sidecar(
        slug="preserve-fields",
        source_board="upwork",
    )
    sidecar["cost"]["total_usd"] = "0.123456"
    sidecar["prompt_templates"] = {"tailoring": "v2", "jd_parse": "v3"}
    sidecar["parsed_jd"] = {"must_haves": ["Python", "FastAPI"], "tone": "neutral"}
    _stage_held_package(out_root, "preserve-fields", sidecar=sidecar)

    client = TestClient(create_app())
    response = client.post(
        "/api/override/preserve-fields",
        json={"reason": "fine by me", "ack_drift": False},
    )
    assert response.status_code == 200

    metadata = json.loads(
        (out_root / "_overridden" / "preserve-fields" / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["source_board"] == "upwork"
    assert metadata["cost"]["total_usd"] == "0.123456"
    assert metadata["prompt_templates"] == {"tailoring": "v2", "jd_parse": "v3"}
    assert metadata["parsed_jd"]["must_haves"] == ["Python", "FastAPI"]
    # Override block records ack_drift=false faithfully.
    assert metadata["override"]["ack_drift"] is False


def test_override_200_writes_metadata_atomically(tmp_path, monkeypatch) -> None:
    """No `.metadata.tmp` should remain after a successful override."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "atomic-slug")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/atomic-slug",
        json={"reason": "ok", "ack_drift": True},
    )
    assert response.status_code == 200

    overridden_dir = out_root / "_overridden" / "atomic-slug"
    files = {p.name for p in overridden_dir.iterdir()}
    assert ".metadata.tmp" not in files
    assert "metadata.json" in files


# ----------------------------- AC4: no outbound submission ---------------


def test_override_does_not_call_notifier(tmp_path, monkeypatch) -> None:
    """The override handler must never invoke `jobhunter.notifier.notify`."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "no-notify-slug")

    with patch("jobhunter.notifier.notify") as notify_spy:
        client = TestClient(create_app())
        response = client.post(
            "/api/override/no-notify-slug",
            json={"reason": "ok", "ack_drift": True},
        )

    assert response.status_code == 200
    assert notify_spy.call_count == 0


# ----------------------------- AC5: unknown slug + held=false ------------


def test_override_404_when_slug_does_not_exist(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    snapshot_before = _snapshot(out_root)

    client = TestClient(create_app())
    response = client.post(
        "/api/override/does-not-exist",
        json={"reason": "ok", "ack_drift": True},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "does-not-exist" in detail
    assert "/api/queue" in detail
    # No directories created.
    assert _snapshot(out_root) == snapshot_before
    assert not (out_root / "_overridden").exists()


def test_override_409_when_package_not_held(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(
        out_root,
        "already-passed",
        sidecar=_held_sidecar(
            slug="already-passed",
            held=False,
            drift={
                "fabrication": "pass",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
        ),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/override/already-passed",
        json={"reason": "ok", "ack_drift": True},
    )

    assert response.status_code == 409
    assert "not_held" in response.json()["detail"]
    # Package unchanged.
    assert (out_root / "already-passed" / "metadata.json").is_file()
    assert not (out_root / "_overridden" / "already-passed").exists()


def test_override_409_when_already_overridden(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(
        out_root,
        "previously-overridden",
        sidecar=_held_sidecar(
            slug="previously-overridden",
            held=False,
            override_applied=True,
        ),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/override/previously-overridden",
        json={"reason": "again?", "ack_drift": True},
    )

    assert response.status_code == 409
    assert "already_overridden" in response.json()["detail"]


def test_override_409_when_destination_already_exists(
    tmp_path, monkeypatch,
) -> None:
    """A leftover `./out/_overridden/<slug>/` must not get clobbered."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _stage_held_package(out_root, "collision-slug")
    # Pre-create a colliding overridden directory (simulates a previous
    # partial override that left state behind).
    overridden_dir = out_root / "_overridden" / "collision-slug"
    overridden_dir.mkdir(parents=True)
    (overridden_dir / "stale.txt").write_text("stale\n", encoding="utf-8")

    client = TestClient(create_app())
    response = client.post(
        "/api/override/collision-slug",
        json={"reason": "ok", "ack_drift": True},
    )

    assert response.status_code == 409
    assert "destination_exists" in response.json()["detail"]
    # Held package untouched.
    assert (out_root / "collision-slug" / "metadata.json").is_file()
    # Stale file untouched.
    assert (overridden_dir / "stale.txt").read_text(encoding="utf-8") == "stale\n"


# ----------------------------- helpers -----------------------------------


def _snapshot(root: Path) -> dict[str, str]:
    """Capture path -> content for every file under *root* (read-only guard)."""
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = path.read_text(
                encoding="utf-8"
            )
    return snapshot
