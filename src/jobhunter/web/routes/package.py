"""Per-package detail route (Story 2.14).

`GET /api/package/{slug}` reads `./out/<slug>/` and returns the JD text, the
tailored CV markdown, the tailored cover letter markdown, the Upwork-proposal
markdown (Story 2.7 lands the artifact; this route surfaces it when present),
and the `metadata.json` sidecar (Story 2.10) as a single JSON payload that the
`/packages/<slug>` review surface consumes.

Slugs that do not exist on disk return `404`. Missing optional artifacts
inside an existing slug directory are returned as `null` — the v1 of Story 1.5
does not persist the raw JD text and Story 2.7 has not landed yet, so the
route is tolerant of those files being absent while preserving the metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from jobhunter.config import PROJECT_ROOT


router = APIRouter()


OUT_ROOT: Path = PROJECT_ROOT / "out"


def _read_optional_text(path: Path) -> str | None:
    """Return the UTF-8 contents of *path* or None if it does not exist."""
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


@router.get("/api/package/{slug}")
def get_package(slug: str) -> dict[str, Any]:
    """Return the artifacts and metadata for a single staged tailoring run."""
    package_dir = OUT_ROOT / slug
    if not package_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"package_not_found: {slug}")

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

    return {
        "slug": slug,
        "jd_text": _read_optional_text(package_dir / "jd.txt"),
        "cv_markdown": _read_optional_text(package_dir / "cv.md"),
        "cover_letter_markdown": _read_optional_text(
            package_dir / "cover-letter.md"
        ),
        "upwork_proposal_markdown": _read_optional_text(
            package_dir / "upwork-proposal.md"
        ),
        "metadata": metadata,
    }
