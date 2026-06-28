"""Regenerate-with-notes route.

`POST /api/package/{slug}/regenerate` re-runs the tailoring pipeline on a
held (or overridden) package using the same JD + canonical CV, but with the
user's correction notes appended to the LLM prompt. The regenerated output
overwrites the same slug directory so the queue stays clean.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jobhunter import config as config_module
from jobhunter.canonical_cv import (
    CanonicalCVMissing,
    UnsupportedCanonicalCVFormat,
    read_canonical_cv,
)
from jobhunter.llm_client import (
    LLMCallFailed,
    LLMResponseInvalid,
    UpworkProposalOverLength,
)
from jobhunter.runtime_config import ConfigurationError, load_runtime_config
from jobhunter.spend_tracker import SpendCapExceeded, SpendLedgerCorrupt
from jobhunter.tailoring import run_tailoring

router = APIRouter()


class RegenerateRequest(BaseModel):
    notes: str = Field(min_length=1)
    jd_text: str | None = None


class RegenerateResponse(BaseModel):
    slug: str
    status: Literal["passed", "held", "failed"]
    cost_usd: str


def _resolve_package_dir(slug: str) -> Path | None:
    out_root = config_module.PROJECT_ROOT / "out"
    primary = out_root / slug
    if primary.is_dir():
        return primary
    overridden = out_root / "_overridden" / slug
    if overridden.is_dir():
        return overridden
    return None


def _read_jd_text(package_dir: Path) -> str | None:
    jd_path = package_dir / "jd.txt"
    if jd_path.is_file():
        return jd_path.read_text(encoding="utf-8").strip() or None

    metadata_path = package_dir / "metadata.json"
    if metadata_path.is_file():
        try:
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            jd = meta.get("jd_text") or meta.get("parsed_jd", {}).get("raw_text")
            if jd:
                return jd
        except (json.JSONDecodeError, AttributeError):
            pass
    return None


def _mark_superseded(package_dir: Path, new_slug: str) -> None:
    """Stamp `superseded_by: <new_slug>` onto the OLD package's metadata.json.

    De-dups the pipeline: the regenerate creates a fresh slug, so the old held
    package would otherwise linger as a duplicate card. `GET /api/queue`
    excludes any sidecar carrying `superseded_by`. Atomic (tmp + os.replace),
    matching the rest of the pipeline; missing/malformed metadata is a no-op so
    a corrupt sidecar can never fail the regenerate that already succeeded.
    """
    metadata_path = package_dir / "metadata.json"
    if not metadata_path.is_file():
        return
    try:
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(meta, dict):
        return
    meta["superseded_by"] = new_slug
    tmp_path = package_dir / ".metadata.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, metadata_path)


def _read_metadata(package_dir: Path) -> dict[str, Any]:
    metadata_path = package_dir / "metadata.json"
    if not metadata_path.is_file():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


@router.post("/api/package/{slug}/regenerate")
def regenerate(slug: str, payload: RegenerateRequest) -> RegenerateResponse:
    package_dir = _resolve_package_dir(slug)
    if package_dir is None:
        raise HTTPException(status_code=404, detail=f"package_not_found: {slug}")

    metadata = _read_metadata(package_dir)
    jd_text = _read_jd_text(package_dir)

    if not jd_text and payload.jd_text:
        jd_text = payload.jd_text.strip()

    if not jd_text:
        raw_text_len = metadata.get("parsed_jd", {}).get("raw_text_length", 0)
        raise HTTPException(
            status_code=422,
            detail=f"no_jd_text_found: the original JD text is not stored in {slug}. "
            f"Paste the JD text in the form to proceed. "
            f"raw_text_length in metadata was {raw_text_len}.",
        )

    notes = payload.notes.strip()
    jd_with_notes = (
        f"{jd_text}\n\n"
        f"## Author Corrections (apply these when regenerating)\n"
        f"{notes}"
    )

    try:
        config = load_runtime_config()
    except ConfigurationError as exc:
        raise HTTPException(status_code=500, detail=f"Configuration error: {exc}") from exc

    try:
        canonical_cv = read_canonical_cv()
    except (UnsupportedCanonicalCVFormat, CanonicalCVMissing) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    source_board = metadata.get("source_board")

    try:
        outcome = run_tailoring(
            canonical_cv,
            jd_with_notes,
            config=config,
            source_board=source_board,
            jd_source=metadata.get("jd_source"),
            url=metadata.get("url"),
            discovered_at=metadata.get("discovered_at"),
        )
    except SpendCapExceeded as exc:
        raise HTTPException(
            status_code=402,
            detail={"error": "monthly_spend_cap_reached", "current_usd": str(exc.current_usd), "cap_usd": str(exc.cap_usd)},
        ) from exc
    except SpendLedgerCorrupt as exc:
        raise HTTPException(status_code=500, detail=f"Spend ledger error: {exc}") from exc
    except (LLMCallFailed, LLMResponseInvalid) as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc
    except UpworkProposalOverLength as exc:
        raise HTTPException(status_code=422, detail={"error": "upwork_proposal_over_length", "word_count": exc.word_count, "max_words": exc.max_words}) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write artifacts: {exc}") from exc

    new_slug = outcome.out_dir.name

    # De-dup: mark the OLD package superseded so it drops out of the queue
    # instead of lingering as a duplicate card alongside the regenerated one.
    # Re-resolve the dir (it may live under `_overridden/`) and never crash if
    # the regenerate itself already moved or removed it.
    old_dir = _resolve_package_dir(slug)
    if old_dir is not None and old_dir != outcome.out_dir:
        _mark_superseded(old_dir, new_slug)

    status: Literal["passed", "held", "failed"] = "passed"
    new_meta_path = outcome.out_dir / "metadata.json"
    if new_meta_path.is_file():
        try:
            new_meta = json.loads(new_meta_path.read_text(encoding="utf-8"))
            if new_meta.get("held"):
                status = "held"
        except json.JSONDecodeError:
            pass

    return RegenerateResponse(
        slug=new_slug,
        status=status,
        cost_usd=format(outcome.result.cost_usd, "f"),
    )
