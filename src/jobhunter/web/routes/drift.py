"""Per-package drift diagnostics route (Story 3.5).

`GET /api/package/{slug}/drift` reads `./out/<slug>/package.drift.json` and
returns the parsed document as-is. The drift report is a top-level dict with
a `fabrication_check` key today (Story 3.2); Stories 4.4 and 5.4 will add
sibling keys (`content_loss`, `keyword_stuffing`) without changing the route.

The route is tolerant of two distinct 404 cases: the slug directory does not
exist on disk (no package was ever staged), and the slug directory exists
but predates the matcher (Epic 1 walking-skeleton runs that have no
`package.drift.json` sidecar).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from jobhunter.config import PROJECT_ROOT


router = APIRouter()


OUT_ROOT: Path = PROJECT_ROOT / "out"


@router.get("/api/package/{slug}/drift")
def get_package_drift(slug: str) -> dict[str, Any]:
    """Return the parsed `package.drift.json` for a single staged package."""
    package_dir = OUT_ROOT / slug
    if not package_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"package_not_found: {slug}")

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
