"""Tailoring orchestration: parse JD → classify → cap check → LLM call → atomic artifact write.

This module is the only place where the spend tracker, the LLM client, and
the artifact directory layout come together. The CLI calls one function:
`run_tailoring(canonical_cv, jd_text, config=...)`.

Story 2.3 adds a structured JD parse step at the top of the orchestration so
every downstream check operates on a stable `parsed_jd` dict (must_haves,
nice_to_haves, tone, seniority, red_flags) rather than re-prompting the LLM
with raw text. The parsed dict is threaded into the metadata sidecar and
surfaced on `TailoringOutcome`.

Story 2.4 inserts a source-board classify step immediately after the parse
so the parsed dict carries `source_board ∈ {upwork, onlinejobs_ph, linkedin,
other}` and the metadata sidecar records the classification.

Atomic write strategy (AC5): build into a `<slug>.tmp` sibling directory,
then `os.replace()` it onto the final path. POSIX guarantees `os.replace()`
is atomic on the same filesystem. On any failure before the rename, the
final `./out/<slug>/` directory is never created.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from jobhunter import (
    artifact_selector,
    board_classifier,
    jd_parser,
    llm_client,
    metadata as metadata_module,
    prompts,
    signals_upwork,
    spend_tracker,
    yaml_config,
)
from jobhunter.board_classifier import Classification
from jobhunter.config import PROJECT_ROOT
from jobhunter.jd_parser import ParseTimedOut, ParsedJD
from jobhunter.llm_client import MODEL_NAME, TailoringResult
from jobhunter.metadata import CallLog, build_metadata, write_sidecar
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.slug import make_slug


__all__ = ["TailoringOutcome", "run_tailoring"]


TailorCallable = Callable[..., TailoringResult]
ParseCallable = Callable[..., ParsedJD]
ClassifyCallable = Callable[..., Classification]


@dataclass(frozen=True)
class TailoringOutcome:
    out_dir: Path
    result: TailoringResult
    spend_before: Decimal
    prompt_versions: dict[str, str]
    parsed_jd: dict = field(default_factory=dict)


def run_tailoring(
    canonical_cv: dict[str, Any],
    jd_text: str,
    *,
    config: RuntimeConfig,
    now: datetime | None = None,
    llm_tailor: TailorCallable | None = None,
    llm_parse: ParseCallable | None = None,
    classify: ClassifyCallable | None = None,
    source_board: str | None = None,
    artifacts_override: list[str] | None = None,
    out_root: Path | None = None,
    ledger_path: Path | None = None,
) -> TailoringOutcome:
    """Orchestrate parse → classify → cap check → tailor → atomic artifact write."""
    using_real_tailor = llm_tailor is None
    tailor = llm_tailor or llm_client.tailor
    parse = llm_parse or jd_parser.parse_jd
    classifier = classify or board_classifier.classify_board
    root = out_root or (PROJECT_ROOT / "out")

    jd_parse_template = prompts.load_prompt("jd_parse")
    try:
        parsed = parse(
            jd_text,
            api_key=config.llm_api_key,
            timeout_seconds=config.llm_call_timeout_seconds,
            prompt=jd_parse_template,
        )
    except ParseTimedOut:
        _write_parse_failure_sidecar(
            root=root,
            jd_text=jd_text,
            now=now,
            error="parse_timeout",
        )
        raise

    classification = classifier(
        jd_text,
        parsed,
        explicit_override=source_board,
    )
    # Story 2.5: when the classifier tags an Upwork JD, run the heuristic
    # signal extractor and surface budget-floor / vague-scope red flags.
    if classification.source_board == "upwork":
        yaml = yaml_config.load_yaml_config()
        upwork_signals = signals_upwork.extract(jd_text)
        parsed.signals["upwork"] = dataclasses.asdict(upwork_signals)
        if signals_upwork.detect_budget_below_floor(
            jd_text,
            hourly_floor=yaml.red_flags.upwork.budget_floor_usd_hourly,
            fixed_floor=yaml.red_flags.upwork.budget_floor_usd_fixed,
        ):
            parsed.red_flags.append(signals_upwork.RED_FLAG_BUDGET_BELOW_FLOOR)
        if signals_upwork.detect_vague_scope(jd_text):
            parsed.red_flags.append(signals_upwork.RED_FLAG_VAGUE_SCOPE)
    # `source_board` lives at the metadata top-level (Story 2.10 placeholder slot).
    # `parsed_jd_dict` stays at Story 2.3's 6-field shape so the structured-parse
    # contract is not mixed with the board-classification concern. `signals` is
    # likewise carried in-memory only (Story 2.5) for the proposal stage (Story 2.7).
    parsed_jd_dict = dataclasses.asdict(parsed)
    parsed_jd_dict.pop("source_board", None)
    parsed_jd_dict.pop("signals", None)

    cv_template = prompts.load_prompt("cv")
    cover_letter_template = prompts.load_prompt("cover_letter")
    loaded_prompts = {"cv": cv_template, "cover_letter": cover_letter_template}
    prompt_versions = {
        "cv": cv_template.version,
        "cover_letter": cover_letter_template.version,
    }

    spend_before = spend_tracker.check_cap_or_raise(
        config.monthly_spend_cap_usd, now=now, ledger_path=ledger_path
    )

    tailor_kwargs: dict[str, Any] = {
        "api_key": config.llm_api_key,
        "timeout_seconds": config.llm_call_timeout_seconds,
    }
    if using_real_tailor:
        tailor_kwargs["prompts"] = loaded_prompts
    result = tailor(canonical_cv, jd_text, **tailor_kwargs)

    spend_tracker.record_call(result.cost_usd, now=now, ledger_path=ledger_path)

    slug = make_slug(jd_text, now=now)
    out_dir = root / slug
    if out_dir.exists():
        raise FileExistsError(out_dir)

    tmp_dir = out_dir.with_name(slug + ".tmp")
    if tmp_dir.exists():
        raise FileExistsError(tmp_dir)

    # Story 2.8 seam: cv.md + cover-letter.md are still written unconditionally
    # here (Stories 1.5/1.6); the selector below decides what `artifacts_produced`
    # records. When source_board="upwork" the list will say "upwork_proposal"
    # even though that file is not written yet — Story 2.7 closes this gap by
    # gating each artifact write on the selector's output.
    tmp_dir.mkdir(parents=True, exist_ok=False)
    try:
        (tmp_dir / "cv.md").write_text(result.cv_markdown, encoding="utf-8")
        (tmp_dir / "cover-letter.md").write_text(
            result.cover_letter_markdown, encoding="utf-8"
        )
        os.replace(tmp_dir, out_dir)
    except Exception:
        _cleanup_tmp(tmp_dir)
        raise

    call_log = CallLog(
        model=MODEL_NAME,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        usd_cost=metadata_module.format_cost(result.cost_usd),
        purpose="tailor_cv_and_cover_letter",
    )
    artifacts_produced = artifact_selector.select(
        classification.source_board,
        explicit_override=artifacts_override,
    )
    package_metadata = build_metadata(
        slug=slug,
        jd_source="paste",
        artifacts_produced=artifacts_produced,
        calls=[call_log],
        prompt_templates=prompt_versions,
        parsed_jd=parsed_jd_dict,
        source_board=classification.source_board,
        now=now,
    )
    write_sidecar(out_dir, package_metadata)

    return TailoringOutcome(
        out_dir=out_dir,
        result=result,
        spend_before=spend_before,
        prompt_versions=prompt_versions,
        parsed_jd=parsed_jd_dict,
    )


def _write_parse_failure_sidecar(
    *,
    root: Path,
    jd_text: str,
    now: datetime | None,
    error: str,
) -> None:
    """Write a minimal metadata sidecar recording a parse-stage failure (AC3)."""
    slug = make_slug(jd_text, now=now)
    out_dir = root / slug
    if out_dir.exists():
        return
    out_dir.mkdir(parents=True, exist_ok=False)
    failure_metadata = build_metadata(
        slug=slug,
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=now,
        error=error,
    )
    write_sidecar(out_dir, failure_metadata)


def _cleanup_tmp(tmp_dir: Path) -> None:
    if not tmp_dir.exists():
        return
    for entry in tmp_dir.iterdir():
        try:
            entry.unlink()
        except OSError:
            pass
    try:
        tmp_dir.rmdir()
    except OSError:
        pass
