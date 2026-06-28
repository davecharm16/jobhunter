"""Story 6.5 AC4: passed + overridden packages are NEVER auto-discarded.

Three on-disk shapes must coexist under `./out/`, all older than the TTL:

1. `./out/held-old/` — has `package.held.json` + `metadata.json`. Story 6.5
   AC2 says this is the ONLY shape that gets swept.
2. `./out/passed-old/` — has `metadata.json` only (no `package.held.json`).
   Drift checks passed, package is recoverable; the sweep must not touch it.
3. `./out/_overridden/over-old/` — released package living under the
   `_overridden/` subtree (Story 6.4). The sweep walks `./out/` non-
   recursively, so this directory is structurally invisible to it.

The sweep is invoked DIRECTLY via `held_package.sweep_expired` (no FastAPI
pipeline) because AC4 is a sweep-level contract, not a routing contract —
the pipeline-level invariant is already pinned by
`test_held_package_sweep.py::test_pipeline_sweep_does_not_touch_passed_packages`
(Story 3.4) and survives the Story 6.5 changes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jobhunter.held_package import AUDIT_LOG_NAME, HELD_SIDECAR_NAME, sweep_expired

FIXED_NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)


def _write_metadata_json(slug_dir: Path, *, slug: str, source_board: str = "upwork",
                         created_at: str | None = None,
                         drift_verdicts: dict[str, str] | None = None,
                         held: bool = False) -> None:
    payload = {
        "slug": slug,
        "source_board": source_board,
        "created_at": created_at
        or (FIXED_NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "drift_verdicts": drift_verdicts or {
            "fabrication": "pass",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
        "held": held,
    }
    (slug_dir / "metadata.json").write_text(
        json.dumps(payload) + "\n", encoding="utf-8"
    )


def _write_held_sidecar(slug_dir: Path, *, held_at: datetime, expires_at: datetime) -> None:
    (slug_dir / HELD_SIDECAR_NAME).write_text(
        json.dumps(
            {
                "held_at": held_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "held_by_check": "fabrication",
                "failed_claims": [{"x": 0}],
                "retention_expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "recoverable": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )


# ---- AC4: only held directories are swept --------------------------------


def test_sweep_only_removes_held_dirs_not_passed_or_overridden(
    tmp_path: Path,
) -> None:
    """The three on-disk shapes (held / passed / overridden) coexist; only held goes."""
    out_root = tmp_path / "out"
    out_root.mkdir()

    # Shape 1: held package, sidecar expired 23 days ago, full metadata.
    held_dir = out_root / "held-old"
    held_dir.mkdir()
    (held_dir / "cv.md").write_text("stale\n", encoding="utf-8")
    held_at = FIXED_NOW - timedelta(days=30)
    expires_at = held_at + timedelta(days=7)
    _write_held_sidecar(held_dir, held_at=held_at, expires_at=expires_at)
    _write_metadata_json(
        held_dir,
        slug="held-old",
        source_board="upwork",
        created_at=held_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        drift_verdicts={
            "fabrication": "fail",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
        held=True,
    )

    # Shape 2: passed package, ancient, NO `package.held.json`.
    passed_dir = out_root / "passed-old"
    passed_dir.mkdir()
    (passed_dir / "cv.md").write_text("good\n", encoding="utf-8")
    _write_metadata_json(passed_dir, slug="passed-old", held=False)

    # Shape 3: overridden package, ancient, lives under `_overridden/`.
    # Even if it carried a `package.held.json` sidecar (it shouldn't —
    # Story 6.4 flips `held=false` on override), the sweep walks `out_root`
    # non-recursively so this directory is never visited.
    overridden_root = out_root / "_overridden"
    overridden_root.mkdir()
    over_dir = overridden_root / "over-old"
    over_dir.mkdir()
    (over_dir / "cv.md").write_text("released\n", encoding="utf-8")
    _write_metadata_json(over_dir, slug="over-old", held=False)

    # Sanity: all three directories exist before the sweep.
    assert held_dir.exists()
    assert passed_dir.exists()
    assert over_dir.exists()

    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)

    # Only the held dir was removed.
    assert discarded == ["held-old"]
    assert not held_dir.exists()
    assert passed_dir.exists()
    assert over_dir.exists()
    # And the `_overridden/` parent itself survives untouched.
    assert overridden_root.exists()

    # The audit log has exactly one entry, for the held slug.
    audit_path = out_root / AUDIT_LOG_NAME
    assert audit_path.is_file()
    lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    assert lines[0]["slug"] == "held-old"
    # Story 6.5 AC3 fields are populated from the held package's metadata.json.
    assert lines[0]["source_board"] == "upwork"
    assert lines[0]["drift_fail_reason"] == "fabrication"
    assert lines[0]["created_at"] == held_at.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_sweep_does_not_recurse_into_overridden_subtree(tmp_path: Path) -> None:
    """An overridden package that still carries a stale `package.held.json` survives.

    Defensive: even if a future Story-6.4 bug left the held sidecar in place
    when moving a package to `_overridden/`, the sweep would still leave it
    alone because `out_root.iterdir()` does not descend into subdirs.
    """
    out_root = tmp_path / "out"
    out_root.mkdir()
    over_dir = out_root / "_overridden" / "buggy-over"
    over_dir.mkdir(parents=True)
    held_at = FIXED_NOW - timedelta(days=30)
    expires_at = held_at + timedelta(days=7)
    _write_held_sidecar(over_dir, held_at=held_at, expires_at=expires_at)
    _write_metadata_json(over_dir, slug="buggy-over", held=False)

    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == []
    assert over_dir.exists()
    assert (over_dir / HELD_SIDECAR_NAME).exists()


def test_sweep_skips_directories_without_held_sidecar(tmp_path: Path) -> None:
    """A passed package's absence of `package.held.json` is the structural marker."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    passed = out_root / "passed-ancient"
    passed.mkdir()
    (passed / "cv.md").write_text("hi\n", encoding="utf-8")
    _write_metadata_json(passed, slug="passed-ancient")
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == []
    assert passed.exists()
    # No audit log was written.
    assert not (out_root / AUDIT_LOG_NAME).is_file()
