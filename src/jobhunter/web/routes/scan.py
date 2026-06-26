"""Job Scan API (spec 2026-06-26). Thin routes; storage injected via get_store."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jobhunter.scan import (
    CandidateInput, ScanStore, validate_settings, validate_site,
)
from jobhunter.scan_store_pg import PostgresScanStore
from jobhunter.web.auth import require_ingest_token

router = APIRouter()


def get_store() -> ScanStore:
    """Production store. Overridden in tests via app.dependency_overrides."""
    return PostgresScanStore.from_env()


class SettingsRequest(BaseModel):
    search_titles: list[str]
    sites_enabled: list[str]
    picks_per_site: int = Field(ge=1, le=10)
    enabled: bool


@router.get("/api/scan/settings")
def get_settings(store: ScanStore = Depends(get_store)) -> dict[str, Any]:
    return store.get_settings().to_dict()


@router.put("/api/scan/settings")
def put_settings(
    payload: SettingsRequest, store: ScanStore = Depends(get_store)
) -> dict[str, Any]:
    try:
        validate_settings(
            payload.search_titles, payload.sites_enabled, payload.picks_per_site
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return store.update_settings(
        search_titles=payload.search_titles,
        sites_enabled=payload.sites_enabled,
        picks_per_site=payload.picks_per_site,
        enabled=payload.enabled,
    ).to_dict()


class CandidatePayload(BaseModel):
    site: str
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str | None = None
    location: str | None = None
    jd_text: str = Field(min_length=1)
    fit_reason: str | None = None
    fit_score: float | None = None


class ResultsRequest(BaseModel):
    started_at: str | None = None
    finished_at: str | None = None
    status: str = "completed"
    site_summary: dict[str, Any] = Field(default_factory=dict)
    candidates: list[CandidatePayload] = Field(default_factory=list)


@router.get("/api/scan/known-urls", dependencies=[Depends(require_ingest_token)])
def known_urls(store: ScanStore = Depends(get_store)) -> dict[str, Any]:
    return {"urls": store.known_urls()}


@router.post("/api/scan/results", dependencies=[Depends(require_ingest_token)])
def post_results(
    payload: ResultsRequest, store: ScanStore = Depends(get_store)
) -> dict[str, Any]:
    for c in payload.candidates:
        try:
            validate_site(c.site)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    cands = [
        CandidateInput(
            site=c.site, url=c.url, title=c.title, company=c.company,
            location=c.location, jd_text=c.jd_text, fit_reason=c.fit_reason,
            fit_score=c.fit_score,
        )
        for c in payload.candidates
    ]
    scan, new, skipped = store.record_scan(
        started_at=payload.started_at, finished_at=payload.finished_at,
        status=payload.status, site_summary=payload.site_summary,
        candidates=cands,
    )
    return {
        "scan_id": scan.id, "received": len(cands), "new": new, "skipped": skipped,
    }


__all__ = ["router", "get_store"]
