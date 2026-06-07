"""Application tracker API (spec 2026-06-07).

Mirrors the existing route style: a module-level `APIRouter`, sync handlers,
no business logic beyond shaping requests/responses. Storage is injected via
the `get_store` dependency so tests override it with an in-memory fake and
production uses the Supabase-backed PostgresApplicationStore.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from jobhunter.application_store_pg import PostgresApplicationStore
from jobhunter.application_tracker import ApplicationStore, validate_status


router = APIRouter()


def get_store() -> ApplicationStore:
    """Production store. Overridden in tests via app.dependency_overrides."""
    return PostgresApplicationStore.from_env()


class CreateApplicationRequest(BaseModel):
    job_title: str = Field(min_length=1)
    slug: str | None = None
    company: str | None = None
    url: str | None = None


class UpdateApplicationRequest(BaseModel):
    status: str | None = None
    notes: str | None = None


@router.post("/api/applications")
def create_application(
    payload: CreateApplicationRequest,
    response: Response,
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    # Idempotency: if this package is already tracked, return the existing row (200).
    if payload.slug:
        existing = store.get_by_slug(payload.slug)
        if existing is not None:
            response.status_code = 200
            return existing.to_dict()
    app = store.create(
        slug=payload.slug,
        job_title=payload.job_title,
        company=payload.company,
        url=payload.url,
    )
    response.status_code = 201
    return app.to_dict()


@router.patch("/api/applications/{app_id}")
def update_application(
    app_id: str,
    payload: UpdateApplicationRequest,
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    if payload.status is not None:
        try:
            validate_status(payload.status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    updated = store.update(app_id, status=payload.status, notes=payload.notes)
    if updated is None:
        raise HTTPException(status_code=404, detail="application not found")
    return updated.to_dict()


@router.get("/api/applications")
def list_applications(
    status: str | None = None,
    store: ApplicationStore = Depends(get_store),
) -> list[dict[str, Any]]:
    if status is not None:
        try:
            validate_status(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return [a.to_dict() for a in store.list(status=status)]


@router.get("/api/applications/{app_id}")
def get_application(
    app_id: str,
    store: ApplicationStore = Depends(get_store),
) -> dict[str, Any]:
    app = store.get(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="application not found")
    body = app.to_dict()
    body["history"] = [h.to_dict() for h in store.history(app_id)]
    return body


__all__ = ["router", "get_store"]
