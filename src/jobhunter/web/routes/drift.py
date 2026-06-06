"""Per-package drift diagnostics routes (Story 3.5, Story D3).

`GET /api/package/{slug}/drift` reads `./out/<slug>/package.drift.json` and
returns the parsed document as-is. The drift report is a top-level dict with
a `fabrication_check` key today (Story 3.2); Stories 4.4 and 5.4 will add
sibling keys (`content_loss`, `keyword_stuffing`) without changing the route.

The route is tolerant of two distinct 404 cases: the slug directory does not
exist on disk (no package was ever staged), and the slug directory exists
but predates the matcher (Epic 1 walking-skeleton runs that have no
`package.drift.json` sidecar).

`GET /api/drift/history` (Story D3) does a single read-pass over `./out/*/`
(and `./out/_overridden/*/`) and returns a list of per-package drift summary
rows sorted newest-first by `created_at`. Dirs lacking `metadata.json` are
silently skipped. Missing or corrupt `package.drift.json` sidecars are
tolerated — the row is still emitted with `drift_verdicts: null` rather than
raising a 500.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobhunter import config as config_module
from jobhunter.config import PROJECT_ROOT


router = APIRouter()


OUT_ROOT: Path = PROJECT_ROOT / "out"

_OVERRIDDEN_DIRNAME = "_overridden"


def _resolve_package_dir_for_drift(slug: str, out_root: Path) -> Path:
    """Return the on-disk directory for *slug*, checking both locations.

    Mirrors the same two-location lookup used by the package detail route:
    first ``out_root/<slug>`` (fresh and held packages), then
    ``out_root/_overridden/<slug>`` (approved/overridden packages). Raises
    ``HTTPException(404)`` if neither exists.
    """
    primary = out_root / slug
    if primary.is_dir():
        return primary
    overridden = out_root / _OVERRIDDEN_DIRNAME / slug
    if overridden.is_dir():
        return overridden
    raise HTTPException(status_code=404, detail=f"package_not_found: {slug}")


# ---------------------------------------------------------------------------
# GET /api/package/{slug}/drift  (Story 3.5)
# ---------------------------------------------------------------------------


@router.get("/api/package/{slug}/drift")
def get_package_drift(slug: str) -> dict[str, Any]:
    """Return the parsed `package.drift.json` for a single staged package.

    Checks both ``out/<slug>/`` and ``out/_overridden/<slug>/`` so that
    approved/overridden packages (which the override flow relocates to the
    ``_overridden`` sub-directory) are found correctly instead of 404-ing.
    """
    package_dir = _resolve_package_dir_for_drift(slug, OUT_ROOT)

    drift_path = package_dir / "package.drift.json"
    if not drift_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"package_drift_not_found: {slug}",
        )

    try:
        return json.loads(drift_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"package_drift_malformed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# GET /api/drift/history  (Story D3)
# ---------------------------------------------------------------------------


class DriftVerdicts(BaseModel):
    fabrication: str | None = None
    content_loss: str | None = None
    keyword_stuffing: str | None = None


class DriftHistoryRow(BaseModel):
    slug: str
    job_title: str | None = None
    company_name: str | None = None
    source_board: str | None = None
    created_at: str | None = None
    drift_verdicts: DriftVerdicts | None = None
    held: bool


class DriftHistoryResponse(BaseModel):
    checks: list[DriftHistoryRow]


def _resolve_out_root() -> Path:
    """Return `./out/` under the current project root (read fresh per call).

    Reading `PROJECT_ROOT` through `config_module` (not the import-time
    constant) lets tests monkeypatch the project root for isolated `out/`
    fixtures — same pattern as the stats and queue routes.
    """
    return config_module.PROJECT_ROOT / "out"


def _read_drift_verdicts(slug_dir: Path) -> DriftVerdicts | None:
    """Read `package.drift.json` and extract the three check verdicts.

    Returns `None` when the file is absent or malformed (the row is still
    emitted — we just omit the verdicts rather than 500-ing).
    """
    drift_path = slug_dir / "package.drift.json"
    if not drift_path.is_file():
        return None
    try:
        doc: dict[str, Any] = json.loads(drift_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    def _verdict(key: str) -> str | None:
        block = doc.get(key)
        if not isinstance(block, dict):
            return None
        raw = block.get("verdict")
        return str(raw) if raw is not None else None

    return DriftVerdicts(
        fabrication=_verdict("fabrication_check"),
        content_loss=_verdict("content_loss"),
        keyword_stuffing=_verdict("keyword_stuffing"),
    )


def _load_rows_from_dir(directory: Path) -> list[DriftHistoryRow]:
    """Load drift-history rows from each slug sub-directory of *directory*.

    Skips the ``_overridden`` meta-directory (iterated separately by the
    caller) and any dir that lacks a ``metadata.json``.
    """
    if not directory.is_dir():
        return []
    rows: list[DriftHistoryRow] = []
    for slug_dir in sorted(directory.iterdir()):
        if not slug_dir.is_dir():
            continue
        if slug_dir.name.startswith("_"):
            continue
        metadata_path = slug_dir / "metadata.json"
        if not metadata_path.is_file():
            continue
        try:
            md: dict[str, Any] = json.loads(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        slug = str(md.get("slug", slug_dir.name))
        verdicts = _read_drift_verdicts(slug_dir)
        rows.append(
            DriftHistoryRow(
                slug=slug,
                job_title=md.get("job_title") or None,
                company_name=md.get("company_name") or None,
                source_board=md.get("source_board") or None,
                created_at=md.get("created_at") or None,
                drift_verdicts=verdicts,
                held=bool(md.get("held", False)),
            )
        )
    return rows


@router.get("/api/drift/history", response_model=DriftHistoryResponse)
def get_drift_history() -> DriftHistoryResponse:
    """Return per-package drift summary rows, newest-first.

    Single read-pass over ``./out/*/`` and ``./out/_overridden/*/``.
    Dirs lacking ``metadata.json`` are silently skipped. Missing or corrupt
    ``package.drift.json`` sidecars are tolerated (row emitted, verdicts
    null). No database involved (DECISIONS.md §6).
    """
    out_root = _resolve_out_root()
    rows = _load_rows_from_dir(out_root)
    overridden_root = out_root / "_overridden"
    rows.extend(_load_rows_from_dir(overridden_root))

    rows.sort(
        key=lambda r: str(r.created_at or ""),
        reverse=True,
    )
    return DriftHistoryResponse(checks=rows)
