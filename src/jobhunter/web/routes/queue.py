"""Queue API routes (Story 6.3).

`GET /api/queue` reads every `./out/<slug>/metadata.json` sidecar from disk via
`jobhunter.stats.load_metadata_sidecars()` and projects each into a queue entry
the Dashboard surface consumes: a `held_count` integer plus a `recent` array
of the ten most-recent packages (created_at descending), each with `{slug,
source_board, verdict, timestamp, job_title, company_name}`.

Story D1 / Dashboard gap 01-1..4: `job_title` and `company_name` are optional
fields surfaced from the metadata sidecar (set by the tailoring pipeline when
it writes the sidecar). When absent the route derives a human-readable title
from the slug (stripping the leading timestamp prefix) and leaves company_name
as None so the UI falls back to source_board gracefully.

Architectural deviation from the original Story 6.3 wording: held packages
live co-located at `./out/<slug>/` (identified by `metadata.held: true`) — not
under a separate `./out/_held/` tree. Stories 3.4 / 4.2 / 5.3 / 6.2 settled
on the co-located layout; the Story 6.2 `notifier.py` docstring documents the
deviation explicitly. This route inherits the same shape.

Per `DECISIONS.md` §6, the route is read-only over `./out/` (no caching layer,
no new persistence) — exactly the same contract as `GET /api/stats`.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter

from jobhunter import config as config_module
from jobhunter.stats import load_metadata_sidecars

# Matches the leading timestamp prefix in slugs (e.g. "20260527T051304Z-").
_SLUG_TIMESTAMP_RE = re.compile(r"^\d{8}T\d{6}Z-")


router = APIRouter()


_RECENT_LIMIT = 10
_DRIFT_FAIL_TO_VERDICT: dict[str, str] = {
    "fabrication": "held:fabrication",
    "content_loss": "held:content-loss",
    "keyword_stuffing": "held:keyword-stuffing",
}


def _resolve_out_root():
    """Return `./out/` under the current project root (read fresh per call)."""
    return config_module.PROJECT_ROOT / "out"


def _classify_verdict(sidecar: dict[str, Any]) -> str:
    """Project a metadata sidecar into one of the six queue verdict labels.

    Resolves `held` + `override.applied` + the `drift_verdicts` fail count
    into a single string the Dashboard surface renders as a badge. A held
    package with zero or more-than-one fail verdicts falls back to
    `held:multiple` so the row is never blank.
    """
    held = bool(sidecar.get("held", False))
    override = sidecar.get("override") or {}
    override_applied = bool(override.get("applied", False))

    if not held:
        if override_applied:
            return "overridden"
        return "pass"

    drift_verdicts = sidecar.get("drift_verdicts") or {}
    failures = [
        key for key, verdict in drift_verdicts.items() if verdict == "fail"
    ]
    if len(failures) == 1:
        return _DRIFT_FAIL_TO_VERDICT.get(failures[0], "held:multiple")
    return "held:multiple"


def _human_title_from_slug(slug: str) -> str:
    """Derive a human-readable title from a slug by stripping the timestamp
    prefix and title-casing the remainder (hyphens → spaces).

    Example: "20260527T051304Z-senior-frontend-developer" → "Senior Frontend Developer"
    """
    bare = _SLUG_TIMESTAMP_RE.sub("", slug)
    return bare.replace("-", " ").title()


def _project_entry(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Project a single sidecar into the recent-queue entry shape.

    ``job_title`` is taken directly from the sidecar when present (written by
    the tailoring pipeline in Story D1). When absent it is derived from the
    slug so the Dashboard surface always has a human-readable label.

    ``company_name`` is optional and may be ``None`` when the sidecar was
    written before Story D1; the UI falls back to ``source_board`` in that
    case.
    """
    slug = str(sidecar.get("slug", ""))
    job_title: str | None = sidecar.get("job_title") or None
    if not job_title:
        job_title = _human_title_from_slug(slug) if slug else None
    company_name: str | None = sidecar.get("company_name") or None

    return {
        "slug": slug,
        "source_board": str(sidecar.get("source_board", "unknown")),
        "verdict": _classify_verdict(sidecar),
        "timestamp": str(sidecar.get("created_at", "")),
        "job_title": job_title,
        "company_name": company_name,
    }


@router.get("/api/queue")
def get_queue() -> dict[str, Any]:
    """Return `held_count` + the ten most-recent packages (held or passed)."""
    out_root = _resolve_out_root()
    sidecars = load_metadata_sidecars(out_root)

    held_count = sum(1 for sidecar in sidecars if bool(sidecar.get("held", False)))

    ordered = sorted(
        sidecars,
        key=lambda sidecar: str(sidecar.get("created_at", "")),
        reverse=True,
    )
    recent = [_project_entry(sidecar) for sidecar in ordered[:_RECENT_LIMIT]]

    return {"held_count": held_count, "recent": recent}


__all__ = ["router"]
