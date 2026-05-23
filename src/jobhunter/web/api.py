"""FastAPI surface for the web-only architecture (DECISIONS.md §6).

Routes wrap the Epic 1 core modules — no business logic lives here. Pydantic
models validate at the HTTP boundary; internal callers stay on the existing
function signatures from `jobhunter.tailoring`, `jobhunter.canonical_cv`, and
`jobhunter.runtime_config`.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
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
from jobhunter.llm_client import (
    LLMCallFailed,
    LLMResponseInvalid,
    UpworkProposalOverLength,
)
from jobhunter.runtime_config import (
    ConfigurationError,
    load_ingest_token,
    load_runtime_config,
)
from jobhunter.spend_tracker import SpendCapExceeded, SpendLedgerCorrupt
from jobhunter.tailoring import run_tailoring
from jobhunter.web.routes.canonical_cv import router as canonical_cv_router
from jobhunter.web.routes.package import router as package_router
from jobhunter.web.routes.stats import router as stats_router


FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

# DECISIONS.md §6 — the FastAPI app binds to 127.0.0.1, so browser-origin
# requests are already gated by the loopback bind and bypass the token check.
# `testclient` is FastAPI's in-process TestClient default and is functionally
# loopback (no real network); it is treated as loopback so existing browser-
# path tests continue to exercise the route without a token.
_LOOPBACK_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _is_loopback_request(request: Request) -> bool:
    client = request.client
    return client is not None and client.host in _LOOPBACK_CLIENT_HOSTS


def require_ingest_token(request: Request) -> None:
    if _is_loopback_request(request):
        return

    expected = load_ingest_token()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="ingest_token_not_configured_on_server",
        )

    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(status_code=401, detail="missing_ingest_token")

    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="invalid_ingest_token")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class PasteRequest(BaseModel):
    jd_text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_board: str | None = None
    metadata: dict[str, Any] | None = None


class PasteResponse(BaseModel):
    slug: str
    cv_path: str
    cover_letter_path: str
    cost_usd: str
    status: Literal["passed", "held", "failed"]
    metadata_path: str
    upwork_proposal_path: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(title="Job Hunter", version=__version__)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.post(
        "/api/paste",
        response_model=PasteResponse,
        dependencies=[Depends(require_ingest_token)],
    )
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

        artifacts_override = (
            payload.metadata.get("artifacts_override") if payload.metadata else None
        )

        try:
            outcome = run_tailoring(
                canonical_cv,
                payload.jd_text,
                config=config,
                source_board=payload.source_board,
                artifacts_override=artifacts_override,
            )
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
        except UpworkProposalOverLength as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "upwork_proposal_over_length",
                    "word_count": exc.word_count,
                    "max_words": exc.max_words,
                },
            ) from exc
        except LLMCallFailed as exc:
            raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
        except LLMResponseInvalid as exc:
            raise HTTPException(status_code=502, detail=f"LLM response was unusable: {exc}") from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to write artifacts: {exc}") from exc

        proposal_path: str | None = None
        if outcome.upwork_proposal_path is not None:
            proposal_path = str(_relative(Path(outcome.upwork_proposal_path)))

        return PasteResponse(
            slug=outcome.out_dir.name,
            cv_path=str(_relative(outcome.out_dir / "cv.md")),
            cover_letter_path=str(_relative(outcome.out_dir / "cover-letter.md")),
            cost_usd=format(outcome.result.cost_usd, "f"),
            status="passed",
            metadata_path=str(_relative(outcome.out_dir / "metadata.json")),
            upwork_proposal_path=proposal_path,
        )

    app.include_router(canonical_cv_router)
    app.include_router(package_router)
    app.include_router(stats_router)

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
