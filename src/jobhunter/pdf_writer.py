"""ATS-friendly PDF export for tailored CVs and cover letters (Story 8.2).

Pure module: accepts markdown string + metadata dict, returns PDF bytes.
No filesystem I/O — callers handle reading/writing.

Engine: WeasyPrint (HTML+CSS -> PDF, text-based searchable output).
Font: Inter (embedded TTF).
Layout: Single column, A4, 0.75-inch margins, no tables/columns/images.
Accent: #4F81BD for name and section headers.
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown
import weasyprint

_FONTS_DIR: Path = Path(__file__).resolve().parent / "web" / "fonts"

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_BASE_CSS = f"""\
@font-face {{
    font-family: 'Inter';
    font-weight: 400;
    src: url('file://{_FONTS_DIR / "Inter-Regular.ttf"}') format('truetype');
}}
@font-face {{
    font-family: 'Inter';
    font-weight: 700;
    src: url('file://{_FONTS_DIR / "Inter-Bold.ttf"}') format('truetype');
}}

@page {{
    size: A4;
    margin: 0.75in;
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: 'Inter', sans-serif;
    font-size: 10.5pt;
    color: #1A202C;
    line-height: 1.45;
}}

/* ---- CV header ---- */
.cv-name {{
    font-size: 20pt;
    font-weight: 700;
    color: #4F81BD;
    margin-bottom: 2pt;
}}

.cv-label {{
    font-size: 13pt;
    font-weight: 700;
    color: #2D3748;
    margin-bottom: 4pt;
}}

.cv-contact {{
    font-size: 9pt;
    color: #718096;
    margin-bottom: 12pt;
}}

/* ---- Section headers (SUMMARY, EXPERIENCE, ...) ---- */
h2 {{
    font-size: 12pt;
    font-weight: 700;
    color: #4F81BD;
    text-transform: uppercase;
    letter-spacing: 0.5pt;
    border-bottom: 0.5pt solid #4F81BD;
    padding-bottom: 3pt;
    margin-top: 14pt;
    margin-bottom: 8pt;
}}

/* ---- Job title lines ---- */
h3 {{
    font-size: 11pt;
    font-weight: 700;
    color: #1A202C;
    margin-top: 10pt;
    margin-bottom: 2pt;
}}

/* Date line (rendered as bold paragraph below h3) */
.date-line {{
    font-size: 10pt;
    font-weight: 700;
    color: #4A5568;
    margin-bottom: 4pt;
}}

/* ---- Body ---- */
p {{
    margin-bottom: 6pt;
}}

ul {{
    margin-left: 0.25in;
    margin-bottom: 6pt;
    list-style-type: disc;
}}

li {{
    margin-bottom: 3pt;
}}

a {{
    color: #4F81BD;
    text-decoration: none;
}}

hr {{
    display: none;
}}

/* ---- Cover-letter specifics ---- */
.cl-body p {{
    margin-bottom: 10pt;
    text-align: left;
}}

.cl-closing {{
    margin-top: 18pt;
}}
"""

# ---------------------------------------------------------------------------
# Markdown -> structured HTML helpers
# ---------------------------------------------------------------------------


_KNOWN_CV_SECTIONS = frozenset({
    "summary", "experience", "skills", "education", "projects",
    "projects & initiatives", "awards", "certifications", "references",
    "languages", "interests", "volunteer", "publications",
})


def _extract_header_from_cv(md: str) -> tuple[str, str, str, str]:
    """Extract name, label, contact line, and remaining body from CV markdown.

    Expected structure at the top of the CV markdown:
        ## Name
        Label line
        contact | info | line
        ---
        ## Summary
        ...

    Returns (name, label, contact_line, body_after_header).
    If the first ``## `` heading is a known section name (e.g. Summary,
    Experience) rather than a person's name, it is left in the body and
    name/label/contact are returned empty.
    """
    lines = md.split("\n")
    name = ""
    label = ""
    contact = ""
    body_start = 0

    i = 0
    # Skip leading blank lines
    while i < len(lines) and not lines[i].strip():
        i += 1

    # Name line: starts with # or ## but is NOT a known section heading
    if i < len(lines) and lines[i].startswith("#"):
        candidate = lines[i].lstrip("# ").strip()
        if candidate.lower() in _KNOWN_CV_SECTIONS:
            remaining = "\n".join(lines[i:])
            return name, label, contact, remaining
        name = candidate
        i += 1

    # Skip blank lines after name
    while i < len(lines) and not lines[i].strip():
        i += 1

    # Label line (non-empty, not a heading, not a rule) — strip **bold**
    if i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("---"):
        label = lines[i].strip().strip("*").strip()
        i += 1

    # Skip blank lines between label and contact
    while i < len(lines) and not lines[i].strip():
        i += 1

    # Contact lines: may span multiple lines (contains @ or | or links or http)
    contact_parts = []
    while i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].startswith("---"):
        line = lines[i].strip()
        if "@" in line or "|" in line or "[" in line or "http" in line:
            # Preserve markdown links here; they become real <a href> anchors
            # later in _contact_to_html so the PDF stays clickable.
            cleaned = line.replace(" | ", " · ").rstrip()
            contact_parts.append(cleaned)
            i += 1
        else:
            break
    contact = " · ".join(contact_parts) if contact_parts else ""

    # Skip until next ## heading or --- rule
    while i < len(lines):
        if lines[i].startswith("## ") or lines[i].startswith("---"):
            break
        i += 1

    # Skip the --- rule if present
    if i < len(lines) and lines[i].startswith("---"):
        i += 1

    body_start = i
    remaining = "\n".join(lines[body_start:])
    return name, label, contact, remaining


def _cv_body_to_html(md_body: str) -> str:
    """Convert the body portion of CV markdown (after header) to HTML.

    Processes ## headings as section headers and ### as job-title lines.
    Handles **Date** bold lines as date lines.
    """
    # Use the markdown library for conversion
    html = markdown.markdown(
        md_body,
        extensions=["extra"],
        output_format="html",
    )

    # Post-process: wrap standalone bold paragraphs that look like dates
    # Pattern: <p><strong>Mon YYYY - Mon YYYY</strong></p>
    html = re.sub(
        r"<p><strong>((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Present)"
        r"[^<]*)</strong></p>",
        r'<p class="date-line">\1</p>',
        html,
    )

    return html


def _build_cv_html(cv_markdown: str, metadata: dict) -> str:
    """Build a complete HTML document for the CV."""
    name, label, contact, body_md = _extract_header_from_cv(cv_markdown)

    # Allow metadata to override if present
    if not name and metadata.get("name"):
        name = metadata["name"]
    if not label and metadata.get("label"):
        label = metadata["label"]

    body_html = _cv_body_to_html(body_md)

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>{_BASE_CSS}</style>
</head>
<body>
<div class="cv-name">{_esc(name)}</div>
<div class="cv-label">{_esc(label)}</div>
<div class="cv-contact">{_contact_to_html(contact)}</div>
{body_html}
</body>
</html>"""


def _extract_header_from_cover_letter(md: str) -> tuple[str, str]:
    """Extract the closing name and body from cover letter markdown.

    Cover letters typically end with:
        Best regards,

        Name

    Returns (body_text, closing_name).
    """
    lines = md.rstrip().split("\n")

    # Find closing — look for "Best regards," or similar from the end
    closing_idx = None
    closing_name = ""
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if re.match(
            r"^(Best regards|Kind regards|Sincerely|Regards|Warm regards|Respectfully),?$",
            stripped,
            re.IGNORECASE,
        ):
            closing_idx = i
            # Name is typically the last non-blank line after closing
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    closing_name = lines[j].strip()
            break

    if closing_idx is not None:
        body = "\n".join(lines[:closing_idx])
    else:
        body = md
        closing_name = ""

    return body, closing_name


def _build_cover_letter_html(
    cover_letter_markdown: str, metadata: dict
) -> str:
    """Build a complete HTML document for the cover letter."""
    body_md, closing_name = _extract_header_from_cover_letter(
        cover_letter_markdown
    )

    # Use metadata for header info
    name = metadata.get("name", closing_name or "")
    label = metadata.get("label", "")
    contact = metadata.get("contact", "")

    # Convert body markdown to HTML
    body_html = markdown.markdown(
        body_md,
        extensions=["extra"],
        output_format="html",
    )

    closing_html = ""
    if closing_name:
        closing_html = f"""\
<div class="cl-closing">
<p>Best regards,</p>
<p><strong>{_esc(closing_name)}</strong></p>
</div>"""

    header_html = ""
    if name:
        header_html += f'<div class="cv-name">{_esc(name)}</div>\n'
    if label:
        header_html += f'<div class="cv-label">{_esc(label)}</div>\n'
    if contact:
        header_html += f'<div class="cv-contact">{_contact_to_html(contact)}</div>\n'
    if header_html:
        header_html += "<br>\n"

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>{_BASE_CSS}</style>
</head>
<body>
{header_html}<div class="cl-body">
{body_html}
</div>
{closing_html}
</body>
</html>"""


def _esc(text: str) -> str:
    """Minimal HTML escaping for plain-text values injected into templates."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _contact_to_html(text: str) -> str:
    """Render a contact line as HTML.

    Converts ``[label](url)`` markdown links into real ``<a href>`` anchors so
    the resulting PDF keeps clickable links (GitHub / LinkedIn / Portfolio).
    All surrounding plain text is HTML-escaped. Text with no links behaves
    identically to ``_esc``.
    """
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        parts.append(_esc(text[last : m.start()]))
        label = _esc(m.group(1))
        url = _esc(m.group(2))
        parts.append(f'<a href="{url}">{label}</a>')
        last = m.end()
    parts.append(_esc(text[last:]))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_cv_pdf(cv_markdown: str, metadata: dict) -> bytes:
    """Convert CV markdown to ATS-friendly PDF bytes.

    Parameters
    ----------
    cv_markdown:
        The full tailored CV in markdown (``## Name`` at top, sections below).
    metadata:
        Dict with optional keys ``name``, ``label``, ``contact`` used as
        fallbacks when the markdown header cannot be parsed.

    Returns
    -------
    bytes
        A valid PDF document (starts with ``%PDF``).
    """
    html = _build_cv_html(cv_markdown, metadata)
    doc = weasyprint.HTML(string=html).write_pdf()
    return doc


def render_cover_letter_pdf(
    cover_letter_markdown: str, metadata: dict
) -> bytes:
    """Convert cover letter markdown to ATS-friendly PDF bytes.

    Parameters
    ----------
    cover_letter_markdown:
        The full tailored cover letter in markdown.
    metadata:
        Dict with optional keys ``name``, ``label``, ``contact`` for the
        header block.  If ``name`` is absent the closing signature line
        is used instead.

    Returns
    -------
    bytes
        A valid PDF document (starts with ``%PDF``).
    """
    html = _build_cover_letter_html(cover_letter_markdown, metadata)
    doc = weasyprint.HTML(string=html).write_pdf()
    return doc
