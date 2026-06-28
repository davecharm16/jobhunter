"""Per-package detail route (Story 2.14, updated Story 8.1).

`GET /api/package/{slug}` reads `./out/<slug>/` and returns the JD text, the
tailored CV markdown, the tailored cover letter markdown, the Upwork-proposal
markdown (Story 2.7 lands the artifact; this route surfaces it when present),
and the `metadata.json` sidecar (Story 2.10) as a single JSON payload that the
`/packages/<slug>` review surface consumes.

Story 8.1 adds a fallback: if `./out/<slug>/` does not exist, the route also
checks `./out/_overridden/<slug>/` — packages that were approved via the
override flow live there after `POST /api/override/{slug}` moves them.

Download endpoints (`GET /api/package/{slug}/download/{filename}`) let the
user retrieve individual markdown artifacts directly. PDF download endpoints
are served by :mod:`jobhunter.web.routes.download` (Story 8.2).

Slugs that do not exist in either location return `404`. Missing optional
artifacts inside an existing slug directory are returned as `null` — the v1 of
Story 1.5 does not persist the raw JD text and Story 2.7 has not landed yet,
so the route is tolerant of those files being absent while preserving the
metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from jobhunter.config import PROJECT_ROOT

router = APIRouter()


OUT_ROOT: Path = PROJECT_ROOT / "out"

_OVERRIDDEN_DIRNAME = "_overridden"


def _resolve_package_dir(slug: str) -> Path:
    """Return the on-disk directory for *slug*, checking both locations.

    First tries ``OUT_ROOT / slug`` (the normal location for fresh and held
    packages). If that directory does not exist, falls back to
    ``OUT_ROOT / "_overridden" / slug`` (where approved packages live after
    the override flow). Raises ``HTTPException(404)`` if neither exists.
    """
    primary = OUT_ROOT / slug
    if primary.is_dir():
        return primary
    overridden = OUT_ROOT / _OVERRIDDEN_DIRNAME / slug
    if overridden.is_dir():
        return overridden
    raise HTTPException(status_code=404, detail=f"package_not_found: {slug}")


def _read_optional_text(path: Path) -> str | None:
    """Return the UTF-8 contents of *path* or None if it does not exist."""
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def read_snapshot_markdown(slug: str) -> tuple[str | None, str | None]:
    """Best-effort read of ``cv.md`` + ``cover-letter.md`` for *slug*.

    Returns ``(cv_markdown, cover_letter_markdown)``, using None for any file
    (or whole package directory) that is absent. Never raises — used by the
    application tracker to snapshot artifacts at apply-time, where a missing
    package must not fail the apply.
    """
    for base in (OUT_ROOT / slug, OUT_ROOT / _OVERRIDDEN_DIRNAME / slug):
        if base.is_dir():
            return (
                _read_optional_text(base / "cv.md"),
                _read_optional_text(base / "cover-letter.md"),
            )
    return (None, None)


@router.get("/api/package/{slug}")
def get_package(slug: str) -> dict[str, Any]:
    """Return the artifacts and metadata for a single staged tailoring run."""
    package_dir = _resolve_package_dir(slug)

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


# --- Download endpoints (Story 8.1) ----------------------------------------


_MD_DOWNLOADS: dict[str, str] = {
    "cv.md": "cv.md",
    "cover-letter.md": "cover-letter.md",
}

@router.get("/api/package/{slug}/download/{filename}")
def download_artifact(slug: str, filename: str) -> Response:
    """Download an individual artifact from a package.

    Markdown files are returned as ``text/markdown`` with a
    ``Content-Disposition: attachment`` header. PDF downloads are handled
    by :mod:`jobhunter.web.routes.download` (Story 8.2).
    """
    disk_name = _MD_DOWNLOADS.get(filename)
    if disk_name is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown_download_artifact: {filename}",
        )

    package_dir = _resolve_package_dir(slug)
    artifact_path = package_dir / disk_name

    if not artifact_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"artifact_not_found: {filename} in {slug}",
        )

    content = artifact_path.read_text(encoding="utf-8")
    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{disk_name}"'},
    )
