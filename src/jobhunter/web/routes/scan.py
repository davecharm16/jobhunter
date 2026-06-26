"""Job Scan API (spec 2026-06-26). Thin routes; storage injected via get_store."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jobhunter.scan import ScanStore, validate_settings
from jobhunter.scan_store_pg import PostgresScanStore

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


__all__ = ["router", "get_store"]
