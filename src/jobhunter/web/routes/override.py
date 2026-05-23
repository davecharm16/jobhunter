"""Override API route (Story 6.4).

`POST /api/override/<slug>` releases a held package only after the operator
explicitly states a non-empty `reason` AND ticks `ack_drift`. The handler
moves `./out/<slug>/` to `./out/_overridden/<slug>/`, re-reads the metadata
sidecar inside the moved directory, stamps a structured `override` block
(`applied`, `reason`, `ack_drift`, `timestamp`) and flips `held` to `false`,
then writes the sidecar back atomically.

Architectural deviation note (matches Stories 6.2 / 6.3): held packages are
co-located at `./out/<slug>/` rather than under a `./out/_held/` tree. The
held state is identified structurally by `metadata.held: true`. After a
successful override the package leaves the co-located tree entirely and
lives under `./out/_overridden/<slug>/` so it cannot be confused with a
fresh held package by a future `GET /api/queue` sweep.

Structural contract (AC4 — no outbound submission):

- This module does NOT import `jobhunter.notifier` (the GChat webhook).
- This module does NOT import `httpx`, `requests`, or `urllib` — there is
  no transport surface here at all. `tests/unit/test_override_imports.py`
  pins this statically.
- The handler is filesystem-only: rename a directory, read+write a JSON
  sidecar. No HTTP client is constructed and no notification function is
  called, structurally guaranteeing FR44 / FR51 compliance.

Atomicity:

- Directory move uses `os.rename` (POSIX-atomic on the same filesystem).
  The repo's `./out/` tree is single-filesystem by convention; if a future
  layout splits it across mounts, swap to `shutil.move` and add a test.
- Metadata write uses the project-standard tmp-sibling + `os.replace`
  idiom from `metadata.write_sidecar`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictBool

from jobhunter import config as config_module
from jobhunter.metadata import now_iso8601_utc


router = APIRouter()


OVERRIDDEN_DIRNAME = "_overridden"


class OverrideRequest(BaseModel):
    """Request body for `POST /api/override/<slug>`.

    Both fields are required and strictly typed:

    - `reason` must be a non-empty string (whitespace-only is rejected).
    - `ack_drift` must be a JSON-body boolean — `StrictBool` rejects the
      string forms `"true"` / `"maybe"` / `"false"`, matching AC2's
      "no string coercion" rule.

    Missing or mistyped fields surface as Pydantic 422 errors whose `loc`
    array names the offending field, so the response body always names
    both required fields when either is missing.
    """

    reason: str = Field(min_length=1)
    ack_drift: StrictBool


def _resolve_out_root() -> Path:
    """Return `./out/` under the current project root (read fresh per call).

    Mirrors `routes/stats.py` and `routes/queue.py`: tests monkeypatch
    `jobhunter.config.PROJECT_ROOT` to point at a per-test tmp fixture and
    rely on this function resolving the value at call time (not at import).
    """
    return config_module.PROJECT_ROOT / "out"


def _strip_whitespace_only(value: str) -> str | None:
    """Return *value* with surrounding whitespace stripped, or None if empty."""
    stripped = value.strip()
    return stripped or None


def _atomic_write_sidecar(metadata_path: Path, payload: dict[str, Any]) -> None:
    """Write *payload* to *metadata_path* via tmp-sibling + `os.replace`.

    Mirrors `jobhunter.metadata.write_sidecar` (which expects a typed
    `PackageMetadata`); the override handler operates on the raw dict it
    re-reads from disk so it does not need to round-trip through the
    dataclass.
    """
    tmp_path = metadata_path.with_name(".metadata.tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, metadata_path)


@router.post("/api/override/{slug}")
def post_override(slug: str, payload: OverrideRequest) -> dict[str, Any]:
    """Release a held package by moving it and stamping override metadata."""
    reason = _strip_whitespace_only(payload.reason)
    if reason is None:
        # `min_length=1` blocks `""`, but a whitespace-only string passes
        # the length check. Reject it with the same 422 shape Pydantic
        # would produce so the contract is uniform.
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "string_too_short",
                    "loc": ["body", "reason"],
                    "msg": "reason must be a non-empty string",
                }
            ],
        )

    out_root = _resolve_out_root()
    package_dir = out_root / slug

    if not package_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=(
                f"package_not_found: {slug} "
                f"(see GET /api/queue for available held packages)"
            ),
        )

    metadata_path = package_dir / "metadata.json"
    if not metadata_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"package_metadata_missing: {slug}",
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"package_metadata_malformed: {exc}",
        ) from exc

    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=500,
            detail=f"package_metadata_malformed: {slug} sidecar is not an object",
        )

    if not bool(metadata.get("held", False)):
        # Two reasons to land here: the package was never held (drift passed)
        # or it has already been overridden in a previous request. Either
        # way the operation is a conflict against the current state.
        override_block = metadata.get("override") or {}
        already_applied = bool(override_block.get("applied", False))
        detail = (
            f"package_already_overridden: {slug}"
            if already_applied
            else f"package_not_held: {slug} (held=false; nothing to release)"
        )
        raise HTTPException(status_code=409, detail=detail)

    overridden_root = out_root / OVERRIDDEN_DIRNAME
    overridden_root.mkdir(parents=True, exist_ok=True)
    destination = overridden_root / slug

    if destination.exists():
        # A previous overridden directory with this slug already exists on
        # disk; refuse to clobber it. Returning 409 here keeps the request
        # safe for retries by an operator who sees the move-but-no-response
        # case (e.g. the response was lost in transit).
        raise HTTPException(
            status_code=409,
            detail=(
                f"override_destination_exists: {slug} already lives under "
                f"./out/{OVERRIDDEN_DIRNAME}/"
            ),
        )

    try:
        os.rename(package_dir, destination)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"override_move_failed: {exc}",
        ) from exc

    moved_metadata_path = destination / "metadata.json"
    metadata["held"] = False
    metadata["override"] = {
        "applied": True,
        "reason": reason,
        "ack_drift": bool(payload.ack_drift),
        "timestamp": now_iso8601_utc(),
    }

    try:
        _atomic_write_sidecar(moved_metadata_path, metadata)
    except OSError as exc:
        # Surface the post-move write failure but do not attempt to roll
        # back the directory rename — the package has already left its
        # held location, and re-renaming on a partial write would be
        # racier than letting the operator fix the sidecar by hand.
        raise HTTPException(
            status_code=500,
            detail=f"override_metadata_write_failed: {exc}",
        ) from exc

    return {
        "slug": slug,
        "overridden": True,
        "moved_to": f"./out/{OVERRIDDEN_DIRNAME}/{slug}/",
        "note": (
            f"Overridden. Open ./out/{OVERRIDDEN_DIRNAME}/{slug}/ and "
            "submit when ready."
        ),
    }


__all__ = ["OVERRIDDEN_DIRNAME", "OverrideRequest", "router"]
