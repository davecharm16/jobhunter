"""F3: regenerate de-dups by marking the OLD package superseded.

A successful `POST /api/package/{slug}/regenerate` creates a new slug. The old
held package must be stamped with `superseded_by: <new_slug>` so it drops out
of `GET /api/queue` instead of lingering as a duplicate card.

The LLM/tailoring layer is stubbed: `run_tailoring`, `load_runtime_config`, and
`read_canonical_cv` are monkeypatched on the route module so the test exercises
only the supersede + queue-exclusion wiring (no network, no env, no real CV).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

import jobhunter.config as config_module
import jobhunter.web.routes.regenerate as regen
from jobhunter.web.api import create_app


def _write_held_package(out_root: Path, slug: str) -> Path:
    pkg = out_root / slug
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "jd.txt").write_text("Original JD body.\n", encoding="utf-8")
    (pkg / "metadata.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "jd_source": "paste",
                "created_at": "2026-05-20T10:00:00Z",
                "source_board": "linkedin",
                "drift_verdicts": {
                    "fabrication": "fail",
                    "content_loss": "pass",
                    "keyword_stuffing": "pass",
                },
                "held": True,
            }
        ),
        encoding="utf-8",
    )
    return pkg


@dataclass
class _FakeResult:
    cost_usd: Decimal


@dataclass
class _FakeOutcome:
    out_dir: Path
    result: _FakeResult


def test_regenerate_marks_old_superseded_and_queue_drops_it(
    tmp_path, monkeypatch
) -> None:
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)

    old_slug = "20260520T100000Z-old-role"
    _write_held_package(out_root, old_slug)

    new_slug = "20260521T120000Z-new-role"

    def _fake_run_tailoring(*_args, **_kwargs):
        new_dir = out_root / new_slug
        new_dir.mkdir(parents=True, exist_ok=True)
        (new_dir / "metadata.json").write_text(
            json.dumps({"slug": new_slug, "held": False}), encoding="utf-8"
        )
        return _FakeOutcome(out_dir=new_dir, result=_FakeResult(Decimal("0.01")))

    monkeypatch.setattr(regen, "run_tailoring", _fake_run_tailoring)
    monkeypatch.setattr(regen, "load_runtime_config", lambda: object())
    monkeypatch.setattr(regen, "read_canonical_cv", lambda: {"basics": {}})

    client = TestClient(create_app())
    resp = client.post(
        f"/api/package/{old_slug}/regenerate", json={"notes": "fix the title"}
    )
    assert resp.status_code == 200
    assert resp.json()["slug"] == new_slug

    # The OLD package's metadata is stamped with superseded_by.
    old_meta = json.loads(
        (out_root / old_slug / "metadata.json").read_text(encoding="utf-8")
    )
    assert old_meta["superseded_by"] == new_slug

    # The queue lists only the new package, not the superseded old one.
    body = client.get("/api/queue").json()
    slugs = [entry["slug"] for entry in body["recent"]]
    assert new_slug in slugs
    assert old_slug not in slugs
    # The superseded held package no longer counts toward held_count.
    assert body["held_count"] == 0
