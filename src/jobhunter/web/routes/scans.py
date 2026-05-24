"""Scans API routes (Story 7.5).

`GET /api/scans` reads every `./out/<slug>/metadata.json` sidecar from disk via
`jobhunter.stats.load_metadata_sidecars()`, filters on `jd_source` in the
n8n-ingest set (`upwork`, `onlinejobs_ph`, `linkedin_email`), and aggregates a
per-flow status row the Job Alerts & Automated Scans surface (Stitch screen
03) renders. Per `DECISIONS.md` §6, no database or new persistence layer is
introduced — telemetry is reconstructed exclusively from on-disk artifacts.

This route surfaces operational telemetry only — never inbox credentials, n8n
auth tokens, IMAP passwords, or any value from `.env`. Aggregations are
derived exclusively from `./out/<slug>/metadata.json` files.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from jobhunter import config as config_module
from jobhunter.stats import load_metadata_sidecars


router = APIRouter()


# The three n8n-ingest channels Story 7.1 / 7.2 / 7.3 / 7.4 introduced. Every
# JD posted through `POST /api/paste` with `source` in this set lands in its
# corresponding flow card; the browser path (`source: "browser"`, `jd_source:
# "paste"`) is intentionally excluded.
_FLOW_NAMES: tuple[str, ...] = ("upwork", "onlinejobs_ph", "linkedin_email")


def _resolve_out_root():
    """Return `./out/` under the current project root (read fresh per call)."""
    return config_module.PROJECT_ROOT / "out"


def _sidecar_timestamp(sidecar: dict[str, Any]) -> str:
    """Return the n8n fetch timestamp (preferred) or fall back to created_at."""
    discovered = sidecar.get("discovered_at")
    if isinstance(discovered, str) and discovered:
        return discovered
    return str(sidecar.get("created_at", ""))


def _is_pass(sidecar: dict[str, Any]) -> bool:
    """Return True iff every drift verdict on the sidecar is `pass`."""
    verdicts = sidecar.get("drift_verdicts") or {}
    if not isinstance(verdicts, dict) or not verdicts:
        return False
    return all(verdict == "pass" for verdict in verdicts.values())


def _aggregate_flow(
    flow_name: str, sidecars: list[dict[str, Any]]
) -> dict[str, Any]:
    """Project the sidecars for one flow into the wire-shape row."""
    matched = [s for s in sidecars if s.get("jd_source") == flow_name]
    if not matched:
        return {
            "flow_name": flow_name,
            "last_run_timestamp": None,
            "last_run_status": "never_run",
            "jds_ingested_count": 0,
            "last_error": None,
        }

    # Most-recent sidecar by timestamp (discovered_at preferred, created_at
    # as the fallback). String comparison is correct because both fields are
    # written as ISO-8601 UTC with a trailing `Z`.
    most_recent = max(matched, key=_sidecar_timestamp)
    status = "pass" if _is_pass(most_recent) else "fail"

    return {
        "flow_name": flow_name,
        "last_run_timestamp": _sidecar_timestamp(most_recent) or None,
        "last_run_status": status,
        "jds_ingested_count": len(matched),
        "last_error": None,
    }


@router.get("/api/scans")
def get_scans() -> dict[str, Any]:
    """Return per-flow ingest telemetry (no credentials, no env values)."""
    out_root = _resolve_out_root()
    sidecars = load_metadata_sidecars(out_root)
    flows = [_aggregate_flow(name, sidecars) for name in _FLOW_NAMES]
    return {"flows": flows}


__all__ = ["router"]
