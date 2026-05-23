"""Stats API routes (Story 2.12).

`GET /api/stats` reads every `./out/<slug>/metadata.json` sidecar from disk via
`jobhunter.stats.load_metadata_sidecars()` and aggregates the per-application
KPIs surfaced on the Dashboard stats card. Per `DECISIONS.md` §6, the
aggregation never opens markdown artifacts and never introduces a database;
sidecars are the only substrate (NFR22).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from jobhunter import config as config_module
from jobhunter import stats as stats_module
from jobhunter.stats import InvalidSinceFilter, aggregate_stats, load_metadata_sidecars


router = APIRouter()


def _resolve_out_root():
    """Return `./out/` under the current project root (read fresh per call).

    Reading `PROJECT_ROOT` through `config_module` (not the import-time
    constant) lets tests monkeypatch the project root for isolated `out/`
    fixtures — same pattern as the canonical-CV routes.
    """
    return config_module.PROJECT_ROOT / "out"


@router.get("/api/stats")
def get_stats(
    since: str | None = Query(default=None),
    board: str | None = Query(default=None),
) -> dict[str, Any]:
    out_root = _resolve_out_root()
    sidecars = load_metadata_sidecars(out_root)
    try:
        aggregate = aggregate_stats(sidecars, since=since, board=board)
    except InvalidSinceFilter as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return aggregate.to_response()


# Re-export for tests that want to monkeypatch the loader / aggregator.
__all__ = ["router", "stats_module"]
