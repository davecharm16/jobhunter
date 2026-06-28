"""Tests for the PDF writer module and download endpoints (Story 8.2).

Covers:
- render_cv_pdf returns valid PDF bytes with searchable text
- render_cover_letter_pdf returns valid PDF bytes with searchable text
- HTTP endpoints return correct Content-Type and Content-Disposition
- 404 for missing slugs and missing artifacts
- Fallback to _overridden/ directory
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from jobhunter.pdf_writer import (
    _build_cover_letter_html,
    _build_cv_html,
    render_cover_letter_pdf,
    render_cv_pdf,
)
from jobhunter.web.api import create_app
from jobhunter.web.routes import download as download_module


def _pdf_link_uris(pdf_bytes: bytes) -> list[str]:
    """Collect all hyperlink (URI) annotations embedded in a PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    uris: list[str] = []
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            obj = annot.get_object()
            action = obj.get("/A")
            if action is not None and action.get("/URI"):
                uris.append(str(action["/URI"]))
    return uris


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract all text from PDF bytes using pypdf."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

# ---------------------------------------------------------------------------
# Sample markdown fixtures
# ---------------------------------------------------------------------------

SAMPLE_CV_MARKDOWN = """\
## Jane Doe
Senior Software Engineer

jane@example.com | +1-555-0100 | [GitHub](https://github.com/janedoe) | [LinkedIn](https://linkedin.com/in/janedoe)

---

## Summary

Experienced software engineer with expertise in Python and distributed systems.

---

## Experience

### Senior Engineer | Acme Corp
**Jan 2022 – Present**

- Built scalable microservices handling 10k requests per second
- Led migration from monolith to event-driven architecture
- Mentored a team of four junior engineers

### Software Engineer | StartupCo
**Mar 2019 – Dec 2021**

- Developed REST APIs using FastAPI and PostgreSQL
- Implemented CI/CD pipelines with GitHub Actions

---

## Skills

**Languages**
- Python, Go, TypeScript, SQL

**Frameworks**
- FastAPI, Django, React, Next.js

---

## Education

**Bachelor of Science in Computer Science**
State University | Graduated May 2019
"""

SAMPLE_COVER_LETTER_MARKDOWN = """\
Dear Hiring Manager,

I am writing to express my interest in the Senior Engineer position at Acme Corp. With my background in distributed systems and Python development, I believe I am well-suited for this role.

In my current position, I have led the migration of a monolithic application to an event-driven microservices architecture, improving system reliability and reducing deployment times by 60%.

I am particularly excited about the opportunity to work on large-scale data processing systems and contribute to the engineering culture at Acme Corp.

Best regards,

Jane Doe
"""


# ---------------------------------------------------------------------------
# Unit tests: render functions
# ---------------------------------------------------------------------------


class TestRenderCvPdf:
    """Tests for render_cv_pdf."""

    def test_returns_valid_pdf_bytes(self) -> None:
        pdf = render_cv_pdf(SAMPLE_CV_MARKDOWN, {})
        assert isinstance(pdf, bytes)
        assert pdf[:5] == b"%PDF-"

    def test_pdf_contains_name(self) -> None:
        pdf = render_cv_pdf(SAMPLE_CV_MARKDOWN, {})
        text = _extract_text(pdf)
        assert "Jane" in text and "Doe" in text

    def test_pdf_contains_section_headers(self) -> None:
        pdf = render_cv_pdf(SAMPLE_CV_MARKDOWN, {})
        text = _extract_text(pdf).upper()
        assert "SUMMARY" in text
        assert "EXPERIENCE" in text

    def test_pdf_contains_work_content(self) -> None:
        pdf = render_cv_pdf(SAMPLE_CV_MARKDOWN, {})
        text = _extract_text(pdf)
        assert "Acme" in text
        assert "microservice" in text.lower() or "scalable" in text.lower()

    def test_metadata_fallback_for_name(self) -> None:
        """When the markdown has no parseable header, metadata is used."""
        bare_md = "## Summary\n\nJust a summary.\n"
        pdf = render_cv_pdf(bare_md, {"name": "Fallback Name"})
        assert pdf[:5] == b"%PDF-"
        text = _extract_text(pdf)
        assert "Fallback" in text

    def test_empty_markdown_still_produces_pdf(self) -> None:
        pdf = render_cv_pdf("", {})
        assert pdf[:5] == b"%PDF-"

    def test_contact_links_become_anchors_in_html(self) -> None:
        """Regression: contact links must survive as real <a href> anchors."""
        md = (
            "## Dave Bulaquena\n"
            "Solutions Designer\n\n"
            "[GitHub](https://github.com/davecharm16) | "
            "[LinkedIn](https://linkedin.com/in/davecharm16) | "
            "[Portfolio](https://portfolio-poc-web.vercel.app)\n\n"
            "---\n\n"
            "## Summary\n\nA short summary.\n"
        )
        html = _build_cv_html(md, {})
        assert '<a href="https://github.com/davecharm16">GitHub</a>' in html
        assert (
            '<a href="https://linkedin.com/in/davecharm16">LinkedIn</a>' in html
        )
        assert (
            '<a href="https://portfolio-poc-web.vercel.app">Portfolio</a>'
            in html
        )

    def test_contact_links_are_clickable_in_pdf(self) -> None:
        """The rendered PDF carries real hyperlink annotations."""
        pdf = render_cv_pdf(SAMPLE_CV_MARKDOWN, {})
        uris = _pdf_link_uris(pdf)
        assert "https://github.com/janedoe" in uris
        assert "https://linkedin.com/in/janedoe" in uris


class TestRenderCoverLetterPdf:
    """Tests for render_cover_letter_pdf."""

    def test_returns_valid_pdf_bytes(self) -> None:
        pdf = render_cover_letter_pdf(SAMPLE_COVER_LETTER_MARKDOWN, {})
        assert isinstance(pdf, bytes)
        assert pdf[:5] == b"%PDF-"

    def test_pdf_contains_body_text(self) -> None:
        pdf = render_cover_letter_pdf(SAMPLE_COVER_LETTER_MARKDOWN, {})
        text = _extract_text(pdf)
        assert "distributed" in text or "monolith" in text

    def test_pdf_contains_closing_name(self) -> None:
        pdf = render_cover_letter_pdf(SAMPLE_COVER_LETTER_MARKDOWN, {})
        text = _extract_text(pdf)
        assert "Jane" in text and "Doe" in text

    def test_metadata_header_in_cover_letter(self) -> None:
        pdf = render_cover_letter_pdf(
            SAMPLE_COVER_LETTER_MARKDOWN,
            {
                "name": "Jane Doe",
                "label": "Senior Engineer",
                "contact": "jane@example.com",
            },
        )
        assert pdf[:5] == b"%PDF-"
        text = _extract_text(pdf)
        assert "Jane" in text

    def test_empty_markdown_still_produces_pdf(self) -> None:
        pdf = render_cover_letter_pdf("", {})
        assert pdf[:5] == b"%PDF-"

    def test_contact_links_become_anchors_in_html(self) -> None:
        """Cover-letter header contact links also render as <a href>."""
        html = _build_cover_letter_html(
            SAMPLE_COVER_LETTER_MARKDOWN,
            {
                "name": "Jane Doe",
                "label": "Senior Engineer",
                "contact": "[GitHub](https://github.com/janedoe)",
            },
        )
        assert '<a href="https://github.com/janedoe">GitHub</a>' in html


# ---------------------------------------------------------------------------
# Integration tests: HTTP endpoints
# ---------------------------------------------------------------------------


@pytest.fixture()
def staged_download_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the download route's OUT_ROOT at a per-test tmp directory."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    monkeypatch.setattr(download_module, "OUT_ROOT", out_root)
    return out_root


def _write_package(
    out_root: Path,
    slug: str,
    *,
    cv_md: str | None = None,
    cl_md: str | None = None,
    metadata: dict | None = None,
    overridden: bool = False,
) -> Path:
    """Stage a package directory with optional artifacts."""
    if overridden:
        package_dir = out_root / "_overridden" / slug
    else:
        package_dir = out_root / slug
    package_dir.mkdir(parents=True)

    if metadata is not None:
        (package_dir / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    if cv_md is not None:
        (package_dir / "cv.md").write_text(cv_md, encoding="utf-8")
    if cl_md is not None:
        (package_dir / "cover-letter.md").write_text(cl_md, encoding="utf-8")
    return package_dir


class TestDownloadCvEndpoint:
    """GET /api/package/{slug}/download/cv.pdf"""

    def test_returns_pdf_with_correct_headers(
        self, staged_download_root: Path
    ) -> None:
        slug = "test-pkg-cv-download"
        _write_package(
            staged_download_root, slug, cv_md=SAMPLE_CV_MARKDOWN
        )

        client = TestClient(create_app())
        resp = client.get(f"/api/package/{slug}/download/cv.pdf")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert f'filename="{slug}-cv.pdf"' in resp.headers["content-disposition"]
        assert resp.content[:5] == b"%PDF-"

    def test_404_for_unknown_slug(
        self, staged_download_root: Path
    ) -> None:
        client = TestClient(create_app())
        resp = client.get("/api/package/nonexistent/download/cv.pdf")
        assert resp.status_code == 404

    def test_404_when_cv_md_missing(
        self, staged_download_root: Path
    ) -> None:
        slug = "test-pkg-no-cv"
        _write_package(staged_download_root, slug, cl_md="Hello.\n")

        client = TestClient(create_app())
        resp = client.get(f"/api/package/{slug}/download/cv.pdf")
        assert resp.status_code == 404
        assert "cv_markdown_not_found" in resp.json()["detail"]

    def test_falls_back_to_overridden_directory(
        self, staged_download_root: Path
    ) -> None:
        slug = "test-pkg-overridden"
        _write_package(
            staged_download_root,
            slug,
            cv_md=SAMPLE_CV_MARKDOWN,
            overridden=True,
        )

        client = TestClient(create_app())
        resp = client.get(f"/api/package/{slug}/download/cv.pdf")

        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"


class TestDownloadCoverLetterEndpoint:
    """GET /api/package/{slug}/download/cover-letter.pdf"""

    def test_returns_pdf_with_correct_headers(
        self, staged_download_root: Path
    ) -> None:
        slug = "test-pkg-cl-download"
        _write_package(
            staged_download_root, slug, cl_md=SAMPLE_COVER_LETTER_MARKDOWN
        )

        client = TestClient(create_app())
        resp = client.get(f"/api/package/{slug}/download/cover-letter.pdf")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert (
            f'filename="{slug}-cover-letter.pdf"'
            in resp.headers["content-disposition"]
        )
        assert resp.content[:5] == b"%PDF-"

    def test_404_for_unknown_slug(
        self, staged_download_root: Path
    ) -> None:
        client = TestClient(create_app())
        resp = client.get(
            "/api/package/nonexistent/download/cover-letter.pdf"
        )
        assert resp.status_code == 404

    def test_404_when_cover_letter_md_missing(
        self, staged_download_root: Path
    ) -> None:
        slug = "test-pkg-no-cl"
        _write_package(staged_download_root, slug, cv_md="# CV\n")

        client = TestClient(create_app())
        resp = client.get(f"/api/package/{slug}/download/cover-letter.pdf")
        assert resp.status_code == 404
        assert "cover_letter_markdown_not_found" in resp.json()["detail"]

    def test_falls_back_to_overridden_directory(
        self, staged_download_root: Path
    ) -> None:
        slug = "test-pkg-cl-overridden"
        _write_package(
            staged_download_root,
            slug,
            cl_md=SAMPLE_COVER_LETTER_MARKDOWN,
            overridden=True,
        )

        client = TestClient(create_app())
        resp = client.get(f"/api/package/{slug}/download/cover-letter.pdf")

        assert resp.status_code == 200
        assert resp.content[:5] == b"%PDF-"
