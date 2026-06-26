"""Job Scan API (spec 2026-06-26). Thin routes; storage injected via get_store."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jobhunter.notifier import build_scan_message, notify_scan
from jobhunter.runtime_config import load_runtime_config
from jobhunter.scan import (
    CandidateInput,
    ScanStore,
    validate_candidate_status,
    validate_settings,
    validate_site,
)
from jobhunter.scan_store_pg import PostgresScanStore
from jobhunter.web.auth import require_ingest_token

router = APIRouter()


def get_store() -> ScanStore:
    """Production store. Overridden in tests via app.dependency_overrides."""
    return PostgresScanStore.from_env()


TailorFn = Callable[[str, str, str], str]  # (jd_text, url, source) -> slug


def get_tailor() -> TailorFn:
    """Production tailor: runs the existing pipeline, returns the new slug.

    Overridden in tests. Keeps DECISIONS.md §4 — the only LLM path is
    run_tailoring()."""
    def _run(jd_text: str, url: str, source: str) -> str:
        from jobhunter.canonical_cv import read_canonical_cv
        from jobhunter.runtime_config import load_runtime_config
        from jobhunter.tailoring import run_tailoring
        outcome = run_tailoring(
            read_canonical_cv(), jd_text, config=load_runtime_config(),
            jd_source=source, url=url or None,
        )
        return outcome.out_dir.name
    return _run


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
    if new > 0:
        try:
            cfg = load_runtime_config()
            webhook = cfg.gchat_webhook_url
        except Exception:  # noqa: BLE001 - config issues must not fail ingest
            webhook = None
        if webhook:
            notify_scan(
                webhook,
                build_scan_message(
                    new_count=new,
                    site_summary=payload.site_summary,
                    dashboard_url="http://127.0.0.1:8765/job-scan",
                ),
            )
    return {
        "scan_id": scan.id, "received": len(cands), "new": new, "skipped": skipped,
    }


class CandidatePatch(BaseModel):
    status: str


@router.get("/api/scan/candidates")
def list_candidates(
    status: str | None = None, scan_id: str | None = None,
    store: ScanStore = Depends(get_store),
) -> list[dict[str, Any]]:
    if status is not None:
        try:
            validate_candidate_status(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [c.to_dict() for c in store.list_candidates(status=status, scan_id=scan_id)]


@router.get("/api/scan/scans")
def list_scans(store: ScanStore = Depends(get_store)) -> list[dict[str, Any]]:
    return [s.to_dict() for s in store.list_scans()]


@router.patch("/api/scan/candidates/{candidate_id}")
def patch_candidate(
    candidate_id: str, payload: CandidatePatch,
    store: ScanStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        validate_candidate_status(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = store.set_candidate_status(candidate_id, status=payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return updated.to_dict()


@router.post("/api/scan/candidates/{candidate_id}/generate")
def generate_from_candidate(
    candidate_id: str,
    store: ScanStore = Depends(get_store),
    tailor: TailorFn = Depends(get_tailor),
) -> dict[str, Any]:
    cand = store.get_candidate(candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    try:
        slug = tailor(cand.jd_text, cand.url, cand.site)
    except Exception as exc:  # noqa: BLE001 - leave candidate retryable
        raise HTTPException(status_code=502, detail=f"tailoring failed: {exc}") from exc
    store.set_candidate_status(candidate_id, status="generated", slug=slug)
    return {"slug": slug, "status": "generated"}


__all__ = ["router", "get_store", "get_tailor"]
