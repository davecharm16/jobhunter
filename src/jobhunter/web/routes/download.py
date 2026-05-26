"""PDF download endpoints for tailored CVs and cover letters (Story 8.2).

``GET /api/package/{slug}/download/cv.pdf``
``GET /api/package/{slug}/download/cover-letter.pdf``

Each endpoint locates the markdown source in ``out/<slug>/`` (falling back to
``out/_overridden/<slug>/``), renders it to an ATS-friendly PDF via
:mod:`jobhunter.pdf_writer`, and streams the result as an attachment.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from jobhunter.config import PROJECT_ROOT
from jobhunter.pdf_writer import render_cover_letter_pdf, render_cv_pdf

router = APIRouter()

OUT_ROOT: Path = PROJECT_ROOT / "out"


def _resolve_package_dir(slug: str) -> Path:
    """Return the package directory for *slug*, checking both locations."""
    primary = OUT_ROOT / slug
    if primary.is_dir():
        return primary
    overridden = OUT_ROOT / "_overridden" / slug
    if overridden.is_dir():
        return overridden
    raise HTTPException(status_code=404, detail=f"package_not_found: {slug}")


def _read_required_text(path: Path, artifact_name: str, slug: str) -> str:
    """Read a required text file or raise 404."""
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"{artifact_name}_not_found: {slug}",
        )
    return path.read_text(encoding="utf-8")


def _load_metadata(package_dir: Path) -> dict:
    """Load metadata.json from the package directory, returning {} on failure."""
    meta_path = package_dir / "metadata.json"
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


@router.get("/api/package/{slug}/download/cv.pdf")
def download_cv_pdf(slug: str) -> Response:
    """Render the tailored CV markdown as a PDF and return it."""
    package_dir = _resolve_package_dir(slug)
    cv_md = _read_required_text(package_dir / "cv.md", "cv_markdown", slug)
    metadata = _load_metadata(package_dir)

    pdf_bytes = render_cv_pdf(cv_md, metadata)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-cv.pdf"',
        },
    )


@router.get("/api/package/{slug}/download/cover-letter.pdf")
def download_cover_letter_pdf(slug: str) -> Response:
    """Render the tailored cover letter markdown as a PDF and return it."""
    package_dir = _resolve_package_dir(slug)
    cl_md = _read_required_text(
        package_dir / "cover-letter.md", "cover_letter_markdown", slug
    )
    metadata = _load_metadata(package_dir)

    pdf_bytes = render_cover_letter_pdf(cl_md, metadata)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{slug}-cover-letter.pdf"'
            ),
        },
    )
