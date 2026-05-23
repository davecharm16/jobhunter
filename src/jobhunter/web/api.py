"""FastAPI surface for the web-only architecture (DECISIONS.md §6).

Routes wrap the Epic 1 core modules — no business logic lives here. Pydantic
models validate at the HTTP boundary; internal callers stay on the existing
function signatures from `jobhunter.tailoring`, `jobhunter.canonical_cv`, and
`jobhunter.runtime_config`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jobhunter import __version__
from jobhunter.canonical_cv import (
    CanonicalCVMissing,
    UnsupportedCanonicalCVFormat,
    read_canonical_cv,
)
from jobhunter.config import PROJECT_ROOT
from jobhunter.llm_client import LLMCallFailed, LLMResponseInvalid
from jobhunter.runtime_config import ConfigurationError, load_runtime_config
from jobhunter.spend_tracker import SpendCapExceeded, SpendLedgerCorrupt
from jobhunter.tailoring import run_tailoring


FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class PasteRequest(BaseModel):
    jd_text: str = Field(min_length=1)
    source: str = Field(min_length=1)


class PasteResponse(BaseModel):
    slug: str
    cv_path: str
    cover_letter_path: str
    cost_usd: str


def create_app() -> FastAPI:
    app = FastAPI(title="Job Hunter", version=__version__)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.post("/api/paste", response_model=PasteResponse)
    def paste(payload: PasteRequest) -> PasteResponse:
        if not payload.jd_text.strip():
            raise HTTPException(status_code=400, detail="jd_text is empty or whitespace-only")

        try:
            config = load_runtime_config()
        except ConfigurationError as exc:
            raise HTTPException(status_code=500, detail=f"Configuration error: {exc}") from exc

        try:
            canonical_cv = read_canonical_cv()
        except UnsupportedCanonicalCVFormat as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except CanonicalCVMissing as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        try:
            outcome = run_tailoring(canonical_cv, payload.jd_text, config=config)
        except SpendCapExceeded as exc:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "monthly_spend_cap_reached",
                    "current_usd": str(exc.current_usd),
                    "cap_usd": str(exc.cap_usd),
                },
            ) from exc
        except SpendLedgerCorrupt as exc:
            raise HTTPException(status_code=500, detail=f"Spend ledger error: {exc}") from exc
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=f"Output slug already exists: {exc}") from exc
        except LLMCallFailed as exc:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
        except LLMResponseInvalid as exc:
            raise HTTPException(status_code=502, detail=f"LLM response was unusable: {exc}") from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to write artifacts: {exc}") from exc

        return PasteResponse(
            slug=outcome.out_dir.name,
            cv_path=str(_relative(outcome.out_dir / "cv.md")),
            cover_letter_path=str(_relative(outcome.out_dir / "cover-letter.md")),
            cost_usd=format(outcome.result.cost_usd, "f"),
        )

    if FRONTEND_DIST.is_dir():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


def _relative(path: Path) -> Path:
    try:
        return path.relative_to(PROJECT_ROOT)
    except ValueError:
        return path


app = create_app()
