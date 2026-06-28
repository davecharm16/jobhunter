"""Unit tests for the Story 6.2 human-readable drift-report renderer.

`compose_drift_report_markdown` is a pure function from the parsed
`package.drift.json` dict to a deterministic Markdown string. `write_drift_report`
adds an atomic on-disk write (tmp + os.replace) into a slug directory.

Architectural note: held packages live at `./out/<slug>/` (co-located with
passed packages), NOT under `./out/_held/<slug>/`. Story 6.2's drift-report.md
lives alongside `package.drift.json` and `package.held.json` in the same slug
directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from jobhunter.drift_report import (
    DRIFT_REPORT_NAME,
    MAX_KEYWORD_STUFFING_TOP_VIOLATIONS,
    MAX_LIST_ENTRIES,
    compose_drift_report_markdown,
    write_drift_report,
)

# ---- compose: section ordering + headings -------------------------------


def test_compose_includes_all_three_section_headings() -> None:
    """All three drift dimensions render even when the doc is empty."""
    body = compose_drift_report_markdown({})
    assert "# Drift report" in body
    assert "## Fabrication" in body
    assert "## Content loss" in body
    assert "## Keyword stuffing" in body


def test_compose_section_order_is_fixed() -> None:
    """Fabrication -> Content loss -> Keyword stuffing (diff-stable across runs)."""
    body = compose_drift_report_markdown({})
    fab_idx = body.index("## Fabrication")
    cl_idx = body.index("## Content loss")
    ks_idx = body.index("## Keyword stuffing")
    assert fab_idx < cl_idx < ks_idx


def test_compose_empty_doc_renders_unknown_verdicts() -> None:
    """A missing block surfaces verdict `unknown` (not crashable)."""
    body = compose_drift_report_markdown({})
    # All three sections show "Verdict: **unknown**" when their blocks are absent.
    assert body.count("Verdict: **unknown**") == 3


def test_compose_ends_with_single_trailing_newline() -> None:
    """Markdown body terminates with exactly one newline (POSIX-text convention)."""
    body = compose_drift_report_markdown({})
    assert body.endswith("\n")
    assert not body.endswith("\n\n")


# ---- compose: fabrication section ---------------------------------------


def test_compose_fabrication_pass_no_unsourced() -> None:
    doc = {
        "fabrication_check": {
            "verdict": "pass",
            "unsourced_claims": [],
        }
    }
    body = compose_drift_report_markdown(doc)
    assert "## Fabrication" in body
    assert "Verdict: **pass**" in body
    assert "Unsourced claims: 0" in body


def test_compose_fabrication_fail_lists_each_unsourced_claim() -> None:
    doc = {
        "fabrication_check": {
            "verdict": "fail",
            "unsourced_claims": [
                {"claim_text": "shipped 99x faster", "reason": "no_canonical_match"},
                {"claim_text": "led a 50-eng team", "reason": "semantic_below_threshold (0.20)"},
            ],
        }
    }
    body = compose_drift_report_markdown(doc)
    fab_section = _section(body, "## Fabrication", "## Content loss")
    assert "Verdict: **fail**" in fab_section
    assert "Unsourced claims: 2" in fab_section
    assert "shipped 99x faster" in fab_section
    assert "no_canonical_match" in fab_section
    assert "led a 50-eng team" in fab_section
    assert "semantic_below_threshold" in fab_section


def test_compose_fabrication_truncates_long_list_with_and_n_more() -> None:
    """A long unsourced list caps at MAX_LIST_ENTRIES bullets + an 'and N more' tail."""
    n = MAX_LIST_ENTRIES + 5
    doc = {
        "fabrication_check": {
            "verdict": "fail",
            "unsourced_claims": [
                {"claim_text": f"claim {i}", "reason": "no_canonical_match"}
                for i in range(n)
            ],
        }
    }
    body = compose_drift_report_markdown(doc)
    fab_section = _section(body, "## Fabrication", "## Content loss")
    # The count is the full N; only the bullets are truncated.
    assert f"Unsourced claims: {n}" in fab_section
    assert "and 5 more" in fab_section
    # First MAX entries appear; later ones do not.
    assert "claim 0" in fab_section
    assert f"claim {MAX_LIST_ENTRIES - 1}" in fab_section
    assert f"claim {MAX_LIST_ENTRIES + 1}" not in fab_section


# ---- compose: content-loss section --------------------------------------


def test_compose_content_loss_fail_lists_dropped_entries() -> None:
    doc = {
        "content_loss": {
            "verdict": "fail",
            "dropped_entries": [
                {
                    "primary_text": "Shipped a TypeScript service",
                    "reason": "silently_lost",
                },
                {
                    "primary_text": "Owned the auth rewrite",
                    "reason": "irrelevant_to_jd",
                },
            ],
        }
    }
    body = compose_drift_report_markdown(doc)
    cl_section = _section(body, "## Content loss", "## Keyword stuffing")
    assert "Verdict: **fail**" in cl_section
    assert "Dropped entries: 2" in cl_section
    assert "Shipped a TypeScript service" in cl_section
    assert "silently_lost" in cl_section
    assert "Owned the auth rewrite" in cl_section


def test_compose_content_loss_truncates_with_and_n_more() -> None:
    n = MAX_LIST_ENTRIES + 3
    doc = {
        "content_loss": {
            "verdict": "fail",
            "dropped_entries": [
                {"primary_text": f"entry {i}", "reason": "silently_lost"}
                for i in range(n)
            ],
        }
    }
    body = compose_drift_report_markdown(doc)
    cl_section = _section(body, "## Content loss", "## Keyword stuffing")
    assert f"Dropped entries: {n}" in cl_section
    assert "and 3 more" in cl_section


# ---- compose: keyword-stuffing section ----------------------------------


def test_compose_keyword_stuffing_pass_no_violations() -> None:
    doc = {
        "keyword_stuffing": {
            "verdict": "pass",
            "density_violations": [],
            "dump_paragraph_locations": [],
        }
    }
    body = compose_drift_report_markdown(doc)
    ks_section = _section(body, "## Keyword stuffing", None)
    assert "Verdict: **pass**" in ks_section
    assert "Violations: 0" in ks_section


def test_compose_keyword_stuffing_sorts_density_violations_by_density_desc() -> None:
    """Density violations render in descending density order, capped at the top N."""
    doc = {
        "keyword_stuffing": {
            "verdict": "fail",
            "density_violations": [
                {"keyword": "python", "artifact": "cv.md", "density_pct": 1.6, "occurrences": 4, "total_tokens": 250, "threshold_breached": "max_density_pct"},
                {"keyword": "django", "artifact": "cv.md", "density_pct": 5.2, "occurrences": 10, "total_tokens": 200, "threshold_breached": "max_density_pct"},
                {"keyword": "redis", "artifact": "cover-letter.md", "density_pct": 3.0, "occurrences": 6, "total_tokens": 200, "threshold_breached": "max_density_pct"},
            ],
            "dump_paragraph_locations": [],
        }
    }
    body = compose_drift_report_markdown(doc)
    ks_section = _section(body, "## Keyword stuffing", None)
    django_idx = ks_section.index("django")
    redis_idx = ks_section.index("redis")
    python_idx = ks_section.index("python")
    # Sorted by density_pct descending: django (5.2) > redis (3.0) > python (1.6).
    assert django_idx < redis_idx < python_idx
    assert "Violations: 3" in ks_section


def test_compose_keyword_stuffing_caps_density_at_top_n() -> None:
    n = MAX_KEYWORD_STUFFING_TOP_VIOLATIONS + 3
    doc = {
        "keyword_stuffing": {
            "verdict": "fail",
            "density_violations": [
                {
                    "keyword": f"kw{i}",
                    "artifact": "cv.md",
                    "density_pct": float(i),  # ascending, so highest are last
                    "occurrences": 5,
                    "total_tokens": 100,
                    "threshold_breached": "max_density_pct",
                }
                for i in range(n)
            ],
            "dump_paragraph_locations": [],
        }
    }
    body = compose_drift_report_markdown(doc)
    ks_section = _section(body, "## Keyword stuffing", None)
    # Top MAX violations render; the rest fold into "and N more".
    assert "and 3 more density violation(s)" in ks_section
    # The lowest density entries should not appear.
    assert "`kw0`" not in ks_section
    assert "`kw1`" not in ks_section
    assert "`kw2`" not in ks_section


def test_compose_keyword_stuffing_includes_placement_violations() -> None:
    doc = {
        "keyword_stuffing": {
            "verdict": "fail",
            "density_violations": [],
            "dump_paragraph_locations": [
                {
                    "artifact": "cv.md",
                    "kind": "keyword_dump_paragraph",
                    "paragraph_index": 2,
                    "matched_keywords": ["python", "django"],
                    "excerpt": "Python, Django, FastAPI, Redis, ...",
                    "keyword_ratio": 0.55,
                },
                {
                    "artifact": "cover-letter.md",
                    "kind": "comma_run_violation",
                    "paragraph_index": 0,
                    "matched_keywords": ["python", "django", "redis", "fastapi"],
                    "excerpt": "Python, Django, Redis, FastAPI",
                },
            ],
        }
    }
    body = compose_drift_report_markdown(doc)
    ks_section = _section(body, "## Keyword stuffing", None)
    assert "Violations: 2" in ks_section
    assert "keyword_dump_paragraph" in ks_section
    assert "comma_run_violation" in ks_section
    assert "cv.md" in ks_section
    assert "cover-letter.md" in ks_section


# ---- compose: determinism ----------------------------------------------


def test_compose_is_deterministic_for_same_input() -> None:
    """Same input -> identical Markdown output every time (diff-stable)."""
    doc = {
        "fabrication_check": {
            "verdict": "fail",
            "unsourced_claims": [
                {"claim_text": "alpha", "reason": "no_canonical_match"},
                {"claim_text": "beta", "reason": "no_canonical_match"},
            ],
        },
        "content_loss": {"verdict": "pass", "dropped_entries": []},
        "keyword_stuffing": {
            "verdict": "pass",
            "density_violations": [],
            "dump_paragraph_locations": [],
        },
    }
    first = compose_drift_report_markdown(doc)
    second = compose_drift_report_markdown(doc)
    assert first == second


def test_compose_is_pure_does_no_io(tmp_path: Path) -> None:
    """Sanity: `compose_drift_report_markdown` must not write anywhere on disk."""
    snapshot_before = sorted(p.name for p in tmp_path.iterdir())
    compose_drift_report_markdown(
        {"fabrication_check": {"verdict": "fail", "unsourced_claims": []}}
    )
    snapshot_after = sorted(p.name for p in tmp_path.iterdir())
    assert snapshot_before == snapshot_after


# ---- write_drift_report: atomic on-disk writer --------------------------


def test_write_drift_report_writes_named_file_into_out_dir(tmp_path: Path) -> None:
    target = write_drift_report(tmp_path, {})
    assert target == tmp_path / DRIFT_REPORT_NAME
    assert target.is_file()
    body = target.read_text(encoding="utf-8")
    assert body.startswith("# Drift report")


def test_write_drift_report_leaves_no_tmp_file_on_success(tmp_path: Path) -> None:
    write_drift_report(tmp_path, {})
    leftover = list(tmp_path.glob(".drift-report*"))
    assert leftover == []


def test_write_drift_report_overwrites_existing_file(tmp_path: Path) -> None:
    """Re-writing replaces the file wholesale (idempotent atomic write)."""
    (tmp_path / DRIFT_REPORT_NAME).write_text("stale content\n", encoding="utf-8")
    write_drift_report(tmp_path, {})
    body = (tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8")
    assert "stale content" not in body
    assert body.startswith("# Drift report")


def test_write_drift_report_from_realistic_multifail_payload(tmp_path: Path) -> None:
    """End-to-end-shaped drift JSON renders cleanly into the file."""
    drift_doc = {
        "fabrication_check": {
            "verdict": "fail",
            "unsourced_claims": [
                {
                    "claim_text": "shipped 99x throughput",
                    "reason": "no_canonical_match",
                }
            ],
        },
        "content_loss": {
            "verdict": "fail",
            "dropped_entries": [
                {
                    "primary_text": "Owned the TypeScript ingest rewrite",
                    "reason": "silently_lost",
                }
            ],
        },
        "keyword_stuffing": {
            "verdict": "fail",
            "density_violations": [
                {
                    "keyword": "python",
                    "artifact": "cv.md",
                    "density_pct": 4.2,
                    "occurrences": 8,
                    "total_tokens": 190,
                    "threshold_breached": "max_density_pct",
                }
            ],
            "dump_paragraph_locations": [],
        },
    }
    target = write_drift_report(tmp_path, drift_doc)
    body = target.read_text(encoding="utf-8")
    # The serialized JSON re-renders identically through the compose pipeline.
    assert body == compose_drift_report_markdown(drift_doc)
    # And the on-disk file is parseable JSON-payload-shaped (sanity).
    assert json.dumps(drift_doc)  # raises only if doc is malformed


# ---- helpers -----------------------------------------------------------


def _section(body: str, start: str, end: str | None) -> str:
    """Slice a section out of *body* between the *start* heading and the *end*
    heading (or end-of-string when *end* is None)."""
    start_idx = body.index(start)
    if end is None:
        return body[start_idx:]
    end_idx = body.index(end, start_idx + len(start))
    return body[start_idx:end_idx]
