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

Story 4.1 inserts the content-loss drift check after the fabrication matcher
+ held-package writer. The check writes `tailoring.trace.json` (empty
`dropped_entries[]` placeholder for now), runs the pure-rule-based matcher
against the produced markdown artifacts, and folds the verdict into
`drift_verdicts["content_loss"]` for `metadata.json`. The `package.drift.json`
content_loss block and held-package extension land in Story 4.2.

Atomic write strategy (AC5): build into a `<slug>.tmp` sibling directory,
then `os.replace()` it onto the final path. POSIX guarantees `os.replace()`
is atomic on the same filesystem. On any failure before the rename, the
final `./out/<slug>/` directory is never created.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from jobhunter import (
    artifact_selector,
    board_classifier,
    claim_extractor,
    content_loss_matcher,
    content_loss_writer,
    drift_report,
    fabrication_matcher,
    held_package,
    jd_parser,
    keyword_stuffing_matcher,
    keyword_stuffing_writer,
    llm_client,
    metadata as metadata_module,
    notifier,
    prompts,
    semantic_matcher,
    signals_onlinejobs_ph,
    signals_upwork,
    spend_tracker,
    yaml_config,
)
from jobhunter.board_classifier import Classification
from jobhunter.claim_extractor import (
    ClaimExtractionResult,
    ClaimExtractionTimedOut,
)
from jobhunter.config import PROJECT_ROOT
from jobhunter.jd_parser import ParseTimedOut, ParsedJD
from jobhunter.llm_client import (
    MODEL_NAME,
    TailoringResult,
    UpworkProposalOverLength,
    UpworkProposalResult,
    count_words,
)
from jobhunter.metadata import CallLog, build_metadata, write_sidecar
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.slug import make_slug


_log = logging.getLogger(__name__)


# PHP → USD conversion for the OJ.ph rate-floor check. Source: Bangko Sentral
# ng Pilipinas reference rate, May 2026 (~PHP 56 per USD). Static here for v1;
# a future story can promote this to config.yaml.
_PHP_PER_USD: Decimal = Decimal("56")


__all__ = ["TailoringOutcome", "run_tailoring"]


TailorCallable = Callable[..., TailoringResult]
TailorUpworkProposalCallable = Callable[..., UpworkProposalResult]
ParseCallable = Callable[..., ParsedJD]
ClassifyCallable = Callable[..., Classification]
ExtractClaimsCallable = Callable[..., ClaimExtractionResult]


# Story 3.1: artifact-name -> on-disk filename mapping used by the
# claim-extraction step. Keys match `artifact_selector.select()` outputs.
_CLAIM_EXTRACTION_SOURCES: dict[str, tuple[str, str]] = {
    "cv": ("cv.md", "cv"),
    "cover_letter": ("cover-letter.md", "cover_letter"),
    "upwork_proposal": ("upwork-proposal.md", "upwork_proposal"),
}


# Heuristic keyword extractor for the screening-question smoke check (AC3).
# A "keyword" is the longest non-stopword token in the question; we log a
# WARNING when none of the question's content words appear in the proposal.
_QUESTION_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "did", "do",
        "does", "for", "from", "have", "how", "i", "if", "in", "is", "it",
        "of", "on", "or", "should", "than", "that", "the", "their", "them",
        "they", "this", "to", "us", "was", "we", "were", "what", "when",
        "where", "which", "who", "why", "will", "with", "would", "you",
        "your", "yours", "have", "any", "more", "much", "many", "some",
        "yes", "no",
    }
)
_QUESTION_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]+")


@dataclass(frozen=True)
class TailoringOutcome:
    out_dir: Path
    result: TailoringResult
    spend_before: Decimal
    prompt_versions: dict[str, str]
    parsed_jd: dict = field(default_factory=dict)
    upwork_proposal_path: str | None = None


def run_tailoring(
    canonical_cv: dict[str, Any],
    jd_text: str,
    *,
    config: RuntimeConfig,
    now: datetime | None = None,
    llm_tailor: TailorCallable | None = None,
    llm_tailor_upwork_proposal: TailorUpworkProposalCallable | None = None,
    llm_parse: ParseCallable | None = None,
    llm_extract_claims: ExtractClaimsCallable | None = None,
    classify: ClassifyCallable | None = None,
    source_board: str | None = None,
    artifacts_override: list[str] | None = None,
    out_root: Path | None = None,
    ledger_path: Path | None = None,
) -> TailoringOutcome:
    """Orchestrate parse → classify → cap check → tailor → extract claims → atomic artifact write."""
    using_real_tailor = llm_tailor is None
    # Back-compat shim: when the caller injected `llm_tailor` (test mode) but
    # did not inject `llm_tailor_upwork_proposal`, default the proposal call
    # to an in-memory stub so existing Epic 2 tests that pre-date Story 2.7
    # continue to pass without an outbound LLM call.
    if llm_tailor_upwork_proposal is None and llm_tailor is not None:
        llm_tailor_upwork_proposal = _stub_upwork_proposal_tailor
    using_real_proposal_tailor = llm_tailor_upwork_proposal is None
    tailor = llm_tailor or llm_client.tailor
    proposal_tailor = llm_tailor_upwork_proposal or llm_client.tailor_upwork_proposal
    parse = llm_parse or jd_parser.parse_jd
    classifier = classify or board_classifier.classify_board
    root = out_root or (PROJECT_ROOT / "out")

    # Story 3.4 AC3: sweep expired held packages BEFORE any LLM work. The
    # sweep is best-effort — any failure is logged and the pipeline continues.
    _run_held_sweep(root, now=now)

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
    # Story 2.6: OJ.ph extractor + rate-below-floor red flag.
    if classification.source_board == "onlinejobs_ph":
        _apply_onlinejobs_ph_signals(parsed, jd_text)
    # `source_board` lives at the metadata top-level (Story 2.10 placeholder slot).
    # `signals` is a board-specific sidecar (Stories 2.5, 2.6) — kept off the
    # `parsed_jd` dict so Story 2.3's 6-field shape is preserved end-to-end.
    parsed_jd_dict = dataclasses.asdict(parsed)
    parsed_jd_dict.pop("source_board", None)
    parsed_jd_dict.pop("signals", None)

    artifacts_produced = artifact_selector.select(
        classification.source_board,
        explicit_override=artifacts_override,
    )
    needs_upwork_proposal = "upwork_proposal" in artifacts_produced

    cv_template = prompts.load_prompt("cv")
    cover_letter_template = prompts.load_prompt("cover_letter")
    loaded_prompts = {"cv": cv_template, "cover_letter": cover_letter_template}
    prompt_versions = {
        "cv": cv_template.version,
        "cover_letter": cover_letter_template.version,
    }
    upwork_proposal_template = None
    if needs_upwork_proposal:
        # Story 2.9 fail-fast contract: missing template raises before any LLM call.
        upwork_proposal_template = prompts.load_prompt("upwork_proposal")
        prompt_versions["upwork_proposal"] = upwork_proposal_template.version

    # Story 3.1: load the claim-extraction prompt up-front so a missing
    # template raises before any LLM call (fail-fast, parallel to the
    # Story 2.9 contract above). The extractor itself runs after the
    # artifacts land on disk in the post-rename block below.
    claims_extract_template = prompts.load_prompt("claims_extract")
    prompt_versions["claims_extract"] = claims_extract_template.version

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

    max_words = (
        yaml_config.load_yaml_config().proposal.max_words
        if needs_upwork_proposal
        else 0
    )

    tmp_dir.mkdir(parents=True, exist_ok=False)
    calls: list[CallLog] = [
        CallLog(
            model=MODEL_NAME,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            usd_cost=metadata_module.format_cost(result.cost_usd),
            purpose="tailor_cv_and_cover_letter",
        )
    ]
    proposal_result: UpworkProposalResult | None = None
    try:
        (tmp_dir / "cv.md").write_text(result.cv_markdown, encoding="utf-8")
        (tmp_dir / "cover-letter.md").write_text(
            result.cover_letter_markdown, encoding="utf-8"
        )

        # Story 2.7: proposal generation lands inside the same tmp_dir so the
        # single os.replace below is atomic across every artifact in the package.
        if needs_upwork_proposal:
            # Second cap check between calls (NFR15) — cap could have been
            # breached by the CV+cover-letter call's own spend record above.
            spend_tracker.check_cap_or_raise(
                config.monthly_spend_cap_usd, now=now, ledger_path=ledger_path
            )

            screening_questions = list(
                parsed.signals.get("upwork", {}).get("screening_questions", [])
            )
            proposal_kwargs: dict[str, Any] = {
                "api_key": config.llm_api_key,
                "timeout_seconds": config.llm_call_timeout_seconds,
                "screening_questions": screening_questions,
                "max_words": max_words,
            }
            if using_real_proposal_tailor and upwork_proposal_template is not None:
                proposal_kwargs["prompt"] = upwork_proposal_template
            proposal_result = proposal_tailor(
                canonical_cv, jd_text, **proposal_kwargs
            )
            spend_tracker.record_call(
                proposal_result.cost_usd, now=now, ledger_path=ledger_path
            )
            calls.append(
                CallLog(
                    model=MODEL_NAME,
                    input_tokens=proposal_result.input_tokens,
                    output_tokens=proposal_result.output_tokens,
                    usd_cost=metadata_module.format_cost(proposal_result.cost_usd),
                    purpose="tailor_upwork_proposal",
                )
            )

            word_count = count_words(proposal_result.proposal_markdown)
            if word_count > max_words:
                raise UpworkProposalOverLength(
                    word_count=word_count, max_words=max_words
                )

            _emit_screening_question_warnings(
                proposal_result.proposal_markdown, screening_questions, slug=slug
            )
            (tmp_dir / "upwork-proposal.md").write_text(
                proposal_result.proposal_markdown, encoding="utf-8"
            )

        os.replace(tmp_dir, out_dir)
    except UpworkProposalOverLength:
        _cleanup_tmp(tmp_dir)
        _write_overlength_failure_sidecar(
            root=root,
            slug=slug,
            parsed_jd=parsed_jd_dict,
            source_board=classification.source_board,
            prompt_versions=prompt_versions,
            calls=calls,
            now=now,
        )
        raise
    except Exception:
        _cleanup_tmp(tmp_dir)
        raise

    upwork_proposal_path: str | None = None
    if needs_upwork_proposal and proposal_result is not None:
        upwork_proposal_path = str(out_dir / "upwork-proposal.md")

    # Story 3.1: extract atomic claims from every produced markdown artifact
    # and write `claims.json`. Each call appends a CallLog entry (AC4 cost
    # logging). On `ClaimExtractionTimedOut`, write a minimal failure sidecar
    # with `error="extraction_timeout"` and re-raise so the route returns 502.
    try:
        _run_claim_extraction(
            out_dir=out_dir,
            artifacts_produced=artifacts_produced,
            calls=calls,
            api_key=config.llm_api_key,
            timeout_seconds=_resolve_extraction_timeout(config),
            prompt=claims_extract_template,
            llm_extract_claims=llm_extract_claims,
        )
    except ClaimExtractionTimedOut:
        _write_extraction_timeout_sidecar(
            out_dir=out_dir,
            slug=slug,
            parsed_jd=parsed_jd_dict,
            source_board=classification.source_board,
            prompt_versions=prompt_versions,
            calls=calls,
            now=now,
        )
        raise

    # Story 3.2: structural fabrication-matcher step. Reads claims.json (just
    # written above), walks the canonical-CV universe, and emits
    # package.drift.json with the fabrication verdict. The package stays
    # "passed" from the pipeline's perspective regardless of verdict (no
    # exception raised). Story 3.4 turns fabrication=fail into a true HELD
    # state below — a `package.held.json` sidecar plus `held=true` on the
    # metadata sidecar. Held vs passed is a metadata distinction, not a
    # control-flow branch: there is exactly one code path through
    # run_tailoring.
    drift_verdicts, fabrication_check = _run_fabrication_matcher(
        out_dir=out_dir, canonical_cv=canonical_cv, config=config
    )

    # Story 4.1: content-loss drift check. Pure rule-based (AC5: zero LLM
    # calls) — projects high-impact canonical-CV entries relevant to the JD,
    # then scans the just-written artifacts for substring presence. The
    # `tailoring.trace.json` write must happen FIRST so the check can pick
    # up any logged drop rationales (AC3). Story 4.2 persists the verdict
    # to `package.drift.json` under the `content_loss` key (sibling to
    # `fabrication_check`) and extends the held-package writer below so a
    # content-loss-only fail also produces a `package.held.json`.
    _write_tailoring_trace(out_dir)
    # Story 4.3: load the content-loss config + build the snapshot once so
    # both the matcher dispatch and the on-disk record reflect the same
    # effective settings for this run.
    content_loss_config = yaml_config.load_yaml_config().drift.content_loss
    content_loss_snapshot = _build_content_loss_snapshot(content_loss_config)
    try:
        content_loss_check = _run_content_loss_check(
            out_dir=out_dir,
            canonical_cv=canonical_cv,
            parsed_jd_dict=parsed_jd_dict,
            artifacts_produced=artifacts_produced,
            config=content_loss_config,
        )
        content_loss_writer.write_content_loss_block(
            out_dir,
            content_loss_check,
            config_snapshot=content_loss_snapshot,
        )
    except content_loss_matcher.EmbeddingMatcherUnavailable as exc:
        # AC2: write a fail-with-error block + verdict; pipeline continues
        # so the package still surfaces a verdict in metadata.
        content_loss_check = content_loss_matcher.ContentLossCheck(
            verdict="fail",
            preserved_entries=[],
            dropped_entries=[],
        )
        content_loss_writer.write_content_loss_block(
            out_dir,
            content_loss_check,
            config_snapshot=content_loss_snapshot,
            error=str(exc),
        )
    drift_verdicts = dict(drift_verdicts)
    drift_verdicts["content_loss"] = content_loss_check.verdict

    # Story 5.1 + 5.2: keyword-stuffing density + placement check. Pure
    # rule-based (AC8: zero LLM calls) — tokenizes each produced markdown
    # artifact, counts each must-have keyword's occurrences, flags per-keyword
    # density / repetition breaches (Story 5.1), and scans paragraphs for
    # dump-paragraph / comma-run violations (Story 5.2). Story 5.3 wires
    # per-channel thresholds from `config.yaml` (shallow-merged over the
    # global defaults via `yaml_config.resolve_keyword_stuffing_thresholds`)
    # and persists the full verdict to `package.drift.json` under the
    # top-level `keyword_stuffing` key.
    keyword_stuffing_config = yaml_config.load_yaml_config().keyword_stuffing
    keyword_stuffing_thresholds = yaml_config.resolve_keyword_stuffing_thresholds(
        keyword_stuffing_config, classification.source_board
    )
    keyword_stuffing_check = _run_keyword_stuffing_check(
        out_dir=out_dir,
        parsed_jd_dict=parsed_jd_dict,
        artifacts_produced=artifacts_produced,
        thresholds=keyword_stuffing_thresholds,
    )
    keyword_stuffing_writer.write_keyword_stuffing_block(
        out_dir,
        keyword_stuffing_check,
        channel=classification.source_board,
        thresholds_applied=keyword_stuffing_thresholds,
    )
    drift_verdicts["keyword_stuffing"] = keyword_stuffing_check.verdict

    # Story 3.4 AC1 + AC2 (extended by Story 4.2 AC6 + Story 5.3 AC4): on
    # fabrication=fail OR content_loss=fail OR keyword_stuffing=fail, write
    # `package.held.json` and record `held=true` + `held_path` on the
    # metadata sidecar. The combined sidecar carries `failed_claims[]`
    # (fabrication side), `dropped_high_impact_entries[]` (content-loss
    # side), and `keyword_stuffing_violations[]` (keyword-stuffing side) so
    # a future `GET /api/queue` can enumerate the fail-cause without
    # re-parsing `package.drift.json`. The held-package writer remains the
    # ONLY post-matcher branch — there is no notification call here,
    # structurally enforcing the no-notify contract.
    held_path_value: str | None = None
    fabrication_failed = fabrication_check.verdict == "fail"
    content_loss_failed = content_loss_check.verdict == "fail"
    keyword_stuffing_failed = keyword_stuffing_check.verdict == "fail"
    if fabrication_failed or content_loss_failed or keyword_stuffing_failed:
        held_path_value = _run_held_package_writer(
            out_dir=out_dir,
            unsourced_claims=(
                fabrication_check.unsourced_claims if fabrication_failed else []
            ),
            dropped_entries=(
                content_loss_check.dropped_entries if content_loss_failed else []
            ),
            keyword_stuffing_check=(
                keyword_stuffing_check if keyword_stuffing_failed else None
            ),
            now=now,
        )
        # Story 6.2 AC2: a human-readable drift-report.md sidecar so the
        # author can read at a glance which check failed and why. Sourced
        # from the machine-readable `package.drift.json` just written by
        # the matchers above; deterministic + zero LLM calls.
        _write_drift_report_markdown(out_dir)

    package_metadata = build_metadata(
        slug=slug,
        jd_source="paste",
        artifacts_produced=artifacts_produced,
        calls=calls,
        prompt_templates=prompt_versions,
        parsed_jd=parsed_jd_dict,
        source_board=classification.source_board,
        drift_verdicts=drift_verdicts,
        now=now,
        held=held_path_value is not None,
        held_path=held_path_value,
    )
    write_sidecar(out_dir, package_metadata)

    # Story 6.1: pass-only GChat notification. All three drift verdicts must
    # be `"pass"` (no `"fail"` or `"pending"`) AND `gchat_webhook_url` must
    # be configured. The webhook call is wrapped so any exception inside
    # the notifier is logged and swallowed — notification failure is
    # non-fatal because the package itself is already on disk. On any
    # outcome (delivered or delivery_failed), the metadata sidecar is
    # re-written with the `notification` field populated. Story 6.2's
    # structural guard pins the no-notify-on-fail contract: the held
    # branch above never reaches this block because `held_path_value`
    # implies at least one fail verdict.
    if (
        held_path_value is None
        and _all_drift_pass(drift_verdicts)
        and config.gchat_webhook_url
    ):
        package_metadata = _notify_and_update_sidecar(
            out_dir=out_dir,
            package_metadata=package_metadata,
            webhook_url=config.gchat_webhook_url,
            now=now,
        )

    return TailoringOutcome(
        out_dir=out_dir,
        result=result,
        spend_before=spend_before,
        prompt_versions=prompt_versions,
        parsed_jd=parsed_jd_dict,
        upwork_proposal_path=upwork_proposal_path,
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


def _apply_onlinejobs_ph_signals(parsed: ParsedJD, jd_text: str) -> None:
    """Populate `parsed.signals['onlinejobs_ph']` and append rate-below-floor red flag (Story 2.6)."""
    signals = signals_onlinejobs_ph.extract(jd_text)
    parsed.signals["onlinejobs_ph"] = dataclasses.asdict(signals)
    rate = signals.rate_range
    if rate is None or rate.min is None:
        return
    floor_usd = yaml_config.load_yaml_config().red_flags.onlinejobs_ph.rate_floor_usd_monthly
    min_usd = (
        Decimal(rate.min)
        if rate.currency == "USD"
        else Decimal(rate.min) / _PHP_PER_USD
    )
    if min_usd < Decimal(floor_usd):
        parsed.red_flags.append("rate_below_floor")


def _stub_upwork_proposal_tailor(
    canonical_cv: dict[str, Any],
    jd_text: str,
    *,
    api_key: str,
    timeout_seconds: float,
    screening_questions: list[str] | None = None,
    max_words: int,
    **_: Any,
) -> UpworkProposalResult:
    """Back-compat in-memory stub for tests that pre-date Story 2.7's proposal call.

    Engaged only when the caller injected `llm_tailor` (signalling test mode)
    but did not yet inject `llm_tailor_upwork_proposal`. Production callers
    (where `llm_tailor is None`) bypass this and hit the real LLM client.
    """
    return UpworkProposalResult(
        proposal_markdown="# Proposal (back-compat stub)\n",
        cost_usd=Decimal("0"),
        input_tokens=0,
        output_tokens=0,
    )


def _write_overlength_failure_sidecar(
    *,
    root: Path,
    slug: str,
    parsed_jd: dict,
    source_board: str,
    prompt_versions: dict[str, str],
    calls: list[CallLog],
    now: datetime | None,
) -> None:
    """Write a failure sidecar after an over-length proposal verdict (AC2)."""
    out_dir = root / slug
    if out_dir.exists():
        return
    out_dir.mkdir(parents=True, exist_ok=False)
    failure_metadata = build_metadata(
        slug=slug,
        jd_source="paste",
        artifacts_produced=[],
        calls=list(calls),
        prompt_templates=prompt_versions,
        parsed_jd=parsed_jd,
        source_board=source_board,
        now=now,
        error="over_length",
    )
    write_sidecar(out_dir, failure_metadata)


def _emit_screening_question_warnings(
    proposal_markdown: str, screening_questions: list[str], *, slug: str
) -> None:
    """Log a WARNING per screening question whose keyword is absent (AC3)."""
    if not screening_questions:
        return
    haystack = proposal_markdown.lower()
    for question in screening_questions:
        keyword = _pick_question_keyword(question)
        if keyword is None:
            continue
        if keyword.lower() not in haystack:
            _log.warning(
                "upwork_proposal smoke check: screening question keyword "
                "%r not found in proposal (slug=%s, question=%r)",
                keyword,
                slug,
                question,
            )


def _pick_question_keyword(question: str) -> str | None:
    """Return the longest non-stopword token in *question*, or None if there is none."""
    candidates = [
        token
        for token in _QUESTION_TOKEN_PATTERN.findall(question)
        if token.lower() not in _QUESTION_STOPWORDS and len(token) > 2
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


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


def _resolve_extraction_timeout(config: RuntimeConfig) -> float:
    """Per-call timeout for the claim-extractor; reads `config.yaml` (Story 3.1 AC4)."""
    try:
        yaml = yaml_config.load_yaml_config()
    except yaml_config.YamlConfigError:
        return float(config.llm_call_timeout_seconds)
    return float(yaml.fabrication.claim_extraction.timeout_seconds)


def _run_claim_extraction(
    *,
    out_dir: Path,
    artifacts_produced: list[str],
    calls: list[CallLog],
    api_key: str,
    timeout_seconds: float,
    prompt: prompts.PromptTemplate,
    llm_extract_claims: ExtractClaimsCallable | None,
) -> None:
    """Extract atomic claims per artifact and write `claims.json` (Story 3.1 AC2-AC4).

    Mutates *calls* in place — each extraction call appends one `CallLog`
    entry with `purpose="extract_claims"` so the deferred `write_sidecar`
    captures the full cost breakdown in a single atomic write.
    """
    extractor = llm_extract_claims or claim_extractor.extract_claims_from_markdown
    all_claims: list[dict[str, Any]] = []
    for artifact_name in artifacts_produced:
        source = _CLAIM_EXTRACTION_SOURCES.get(artifact_name)
        if source is None:
            continue
        filename, source_label = source
        artifact_path = out_dir / filename
        if not artifact_path.is_file():
            continue
        markdown_text = artifact_path.read_text(encoding="utf-8")
        extract_result = extractor(
            markdown_text,
            source_label,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            prompt=prompt,
        )
        calls.append(
            CallLog(
                model=MODEL_NAME,
                input_tokens=extract_result.input_tokens,
                output_tokens=extract_result.output_tokens,
                usd_cost=metadata_module.format_cost(extract_result.cost_usd),
                purpose="extract_claims",
            )
        )
        all_claims.extend(
            dataclasses.asdict(claim) for claim in extract_result.claims
        )

    # AC2: claims.json is a single JSON array of Claim objects (downstream
    # Story 3.2 consumes this shape). Atomic write via tmp + os.replace so
    # a crash mid-write cannot leave a half-written file on disk.
    target = out_dir / "claims.json"
    tmp_path = out_dir / ".claims.tmp"
    tmp_path.write_text(json.dumps(all_claims, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, target)


def _run_fabrication_matcher(
    *,
    out_dir: Path,
    canonical_cv: dict[str, Any],
    config: RuntimeConfig,
) -> tuple[dict[str, str], fabrication_matcher.FabricationCheck]:
    """Run the Story 3.2 structural matcher and write `package.drift.json`.

    Reads `claims.json` from disk (already written by the Story 3.1 step),
    rebuilds typed `Claim` dataclasses, hands them to `run_matcher` (with
    Story 3.3's semantic step injected), writes the drift report, and
    returns the `drift_verdicts` dict the metadata sidecar consumes
    alongside the raw `FabricationCheck` so the Story 3.4 held-package
    writer can compose `package.held.json` from the same matcher output.
    `content_loss` and `keyword_stuffing` stay "pending" until Epics 4
    and 5 land their checks.
    """
    claims_path = out_dir / "claims.json"
    raw = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = [
        claim_extractor.Claim(
            claim_id=item["claim_id"],
            claim_type=item["claim_type"],
            claim_text=item["claim_text"],
            source_artifact=item["source_artifact"],
            line_number=item["line_number"],
        )
        for item in raw
    ]
    # Story 3.3: build the semantic step from yaml-configured method +
    # threshold, with a `rejection_reasons` side-channel so the specific
    # `semantic_below_threshold` / `quantifier_not_in_source` reasons can
    # override `run_matcher`'s generic `no_canonical_match` fallback.
    yaml = yaml_config.load_yaml_config()
    rejection_reasons: dict[str, str] = {}
    semantic_step = semantic_matcher.make_semantic_step(
        method=yaml.fabrication.semantic_method,
        threshold=float(yaml.fabrication.semantic_threshold),
        api_key=config.llm_api_key,
        rejection_reasons=rejection_reasons,
    )
    check = fabrication_matcher.run_matcher(
        claims, canonical_cv, semantic_step=semantic_step
    )
    check = _upgrade_unsourced_reasons(check, rejection_reasons)
    fabrication_matcher.write_drift_report(out_dir, check)
    verdicts = {
        "fabrication": check.verdict,
        "content_loss": "pending",
        "keyword_stuffing": "pending",
    }
    return verdicts, check


def _run_held_package_writer(
    *,
    out_dir: Path,
    unsourced_claims: list[fabrication_matcher.UnsourcedClaim],
    dropped_entries: list[content_loss_matcher.DroppedEntry] | None = None,
    keyword_stuffing_check: keyword_stuffing_matcher.KeywordStuffingCheck | None = None,
    now: datetime | None,
) -> str:
    """Compose + atomically write `package.held.json`; return its path string (Story 3.4 AC1).

    Story 4.2 AC6 extends the signature with *dropped_entries*: when the
    content-loss check contributes to the held verdict, its `silently_lost`
    drops are persisted under `dropped_high_impact_entries[]` on the same
    sidecar. Story 5.3 AC4 extends it with *keyword_stuffing_check*: a
    failing keyword-stuffing check projects its density + placement
    violations into `keyword_stuffing_violations[]` on the same sidecar.
    Both arguments are keyword-only and default to `None` so Story
    3.4/4.2's call sites stay source-compatible.
    """
    retention_days = _resolve_held_retention_days()
    moment = now or datetime.now(timezone.utc)
    record = held_package.compose_held_record(
        unsourced_claims,
        out_dir,
        now=moment,
        retention_days=retention_days,
        dropped_entries=dropped_entries,
        keyword_stuffing_check=keyword_stuffing_check,
    )
    held_path = held_package.write_held_sidecar(out_dir, record)
    return str(held_path)


def _run_held_sweep(root: Path, *, now: datetime | None) -> None:
    """Sweep expired held packages off disk; best-effort (Story 3.4 AC3, Story 6.5 AC2).

    Invoked at the top of `run_tailoring` before any LLM work. Any failure
    is logged at WARNING and swallowed — the sweep must never abort the
    pipeline that just started running.

    Story 6.5 AC1: when the resolved TTL is `0` the sweep is skipped
    entirely (the queue is kept forever). The early-return is paired with
    `held_package.sweep_expired`'s own `retention_days == 0` guard so
    direct callers of the sweep function get the same disabled behavior.
    """
    try:
        retention_days = _resolve_held_retention_days()
        if retention_days == 0:
            _log.debug("held-package sweep disabled (held_package_ttl_days=0)")
            return
        moment = now or datetime.now(timezone.utc)
        discarded = held_package.sweep_expired(
            root, now=moment, retention_days=retention_days
        )
        if discarded:
            _log.info(
                "held-package sweep discarded %d expired package(s): %s",
                len(discarded),
                ", ".join(discarded),
            )
    except Exception as exc:
        _log.warning("held-package sweep failed: %s", exc)


def _resolve_held_retention_days() -> int:
    """Pull the held-package TTL from `config.yaml` (Story 6.5 AC1 precedence).

    Reads the top-level `held_package_ttl_days` key first; falls back to the
    deprecated `fabrication.held_retention_days` when the new key is absent
    (the loader emits a `DeprecationWarning` on the legacy path). Default is
    7. A value of `0` means "disable the sweep" — caller short-circuits.
    """
    try:
        yaml = yaml_config.load_yaml_config()
    except yaml_config.YamlConfigError:
        return 7
    return int(yaml.held_package_ttl_days)


def _upgrade_unsourced_reasons(
    check: fabrication_matcher.FabricationCheck,
    rejection_reasons: dict[str, str],
) -> fabrication_matcher.FabricationCheck:
    """Replace generic `no_canonical_match` reasons with Story-3.3 specifics.

    `fabrication_matcher.run_matcher` (frozen in Story 3.3) hard-codes
    `reason="no_canonical_match"` whenever the semantic step returns None.
    The semantic step recorded the specific reason
    (`semantic_below_threshold (...)` or `quantifier_not_in_source (...)`)
    in *rejection_reasons* keyed by claim_id; this pass swaps in those
    reasons so the drift report carries the AC2/AC3 wording.
    """
    if not rejection_reasons:
        return check
    new_unsourced = []
    for entry in check.unsourced_claims:
        specific = rejection_reasons.get(entry.claim_id)
        if specific is None or entry.reason != "no_canonical_match":
            new_unsourced.append(entry)
            continue
        new_unsourced.append(
            fabrication_matcher.UnsourcedClaim(
                claim_id=entry.claim_id,
                claim_text=entry.claim_text,
                source_artifact=entry.source_artifact,
                line_number=entry.line_number,
                reason=specific,
            )
        )
    return fabrication_matcher.FabricationCheck(
        verdict=check.verdict,
        claims_total=check.claims_total,
        claims_sourced=check.claims_sourced,
        claims_unsourced=check.claims_unsourced,
        traces=check.traces,
        unsourced_claims=new_unsourced,
    )


# Story 4.1: artifact-name -> on-disk filename mapping used by the
# content-loss check's presence scan. Kept in fixed insertion order (cv ->
# cover_letter -> upwork_proposal) so the produced `matched_in` lists in
# the drift report are diff-stable across runs (Story 4.2 will assert this).
_CONTENT_LOSS_ARTIFACT_FILENAMES: dict[str, str] = {
    "cv": "cv.md",
    "cover_letter": "cover-letter.md",
    "upwork_proposal": "upwork-proposal.md",
}


def _write_tailoring_trace(out_dir: Path) -> Path:
    """Write `tailoring.trace.json` with an empty `dropped_entries[]` (Story 4.1 AC3).

    v1 placeholder shape so the content-loss check has a stable file to
    consume. Future tailoring stories (or manual author edits) can populate
    `dropped_entries[]` with `{entry_id, reason}` records to suppress
    `silently_lost` verdicts for intentional drops. Atomic write idiom
    (tmp + os.replace) matches the rest of the pipeline.
    """
    target = out_dir / "tailoring.trace.json"
    tmp_path = out_dir / ".tailoring.trace.tmp"
    payload = {"dropped_entries": []}
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, target)
    return target


def _read_tailoring_trace(out_dir: Path) -> list[dict[str, Any]]:
    """Read and parse `tailoring.trace.json`; tolerates missing / malformed files (AC3)."""
    trace_path = out_dir / "tailoring.trace.json"
    if not trace_path.is_file():
        return []
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning(
            "content-loss check: could not parse %s (%s); treating trace as empty",
            trace_path,
            exc,
        )
        return []
    if not isinstance(payload, dict):
        return []
    dropped = payload.get("dropped_entries")
    if not isinstance(dropped, list):
        return []
    return dropped


def _run_content_loss_check(
    *,
    out_dir: Path,
    canonical_cv: dict[str, Any],
    parsed_jd_dict: dict[str, Any],
    artifacts_produced: list[str],
    config: yaml_config.ContentLossConfig | None = None,
) -> content_loss_matcher.ContentLossCheck:
    """Run the Story 4.1 content-loss matcher (Story 4.3 config-aware) and return its verdict.

    Pure rule-based check — makes ZERO LLM calls (AC5) on the default
    matcher modes. `embedding_distance` and `semantic` raise
    `EmbeddingMatcherUnavailable` (no embeddings client wired in v1).
    """
    artifact_paths: dict[str, Path] = {}
    for artifact_name in artifacts_produced:
        filename = _CONTENT_LOSS_ARTIFACT_FILENAMES.get(artifact_name)
        if filename is None:
            continue
        path = out_dir / filename
        if not path.is_file():
            continue
        artifact_paths[filename] = path
    dropped_trace = _read_tailoring_trace(out_dir)
    relevant = content_loss_matcher.iter_high_impact_relevant(
        canonical_cv, parsed_jd_dict, config=config
    )
    return content_loss_matcher.run_check(
        relevant, artifact_paths, dropped_trace, config=config
    )


def _run_keyword_stuffing_check(
    *,
    out_dir: Path,
    parsed_jd_dict: dict[str, Any],
    artifacts_produced: list[str],
    thresholds: dict[str, Any],
) -> keyword_stuffing_matcher.KeywordStuffingCheck:
    """Run the keyword-stuffing density + placement check and return the verdict.

    Pure rule-based check — makes ZERO LLM calls (AC8). Reads each
    produced markdown artifact, tokenizes, counts each must-have keyword
    (Story 5.1 density / repetition dimension), and additionally splits
    each artifact into paragraphs to flag dump paragraphs and comma-run
    violations (Story 5.2 placement dimension). The two dimensions are
    OR-ed into the verdict: a package fails if EITHER density OR
    placement reports a violation. Story 5.3 threads the resolved
    per-channel thresholds in via *thresholds* — produced by
    `yaml_config.resolve_keyword_stuffing_thresholds(config, channel)`.
    """
    must_haves = parsed_jd_dict.get("must_haves") or []
    if not isinstance(must_haves, list):
        must_haves = []
    artifact_paths: dict[str, Path] = {}
    for artifact_name in artifacts_produced:
        filename = _CONTENT_LOSS_ARTIFACT_FILENAMES.get(artifact_name)
        if filename is None:
            continue
        path = out_dir / filename
        if not path.is_file():
            continue
        artifact_paths[filename] = path
    return keyword_stuffing_matcher.run_keyword_stuffing_check(
        artifact_paths,
        must_haves,
        max_density_pct=float(thresholds["max_density_pct"]),
        max_repetitions_per_artifact=int(
            thresholds["max_repetitions_per_artifact"]
        ),
        dump_paragraph_min_tokens=int(thresholds["dump_paragraph_min_tokens"]),
        dump_paragraph_max_keyword_ratio=float(
            thresholds["dump_paragraph_max_keyword_ratio"]
        ),
        comma_run_min_tokens=int(thresholds["comma_run_min_tokens"]),
    )


def _build_content_loss_snapshot(
    config: yaml_config.ContentLossConfig,
) -> dict[str, Any]:
    """Project the effective content-loss config into the drift.json snapshot (Story 4.3 AC4).

    Only the fields relevant to the chosen matcher mode are surfaced —
    e.g. `keyword_overlap_pct` is omitted unless `relevance_matcher` is
    `keyword_overlap`.
    """
    snapshot: dict[str, Any] = {
        "relevance_matcher": config.relevance_matcher,
        "presence_matcher": config.presence_matcher,
    }
    if config.relevance_matcher == "tag_overlap":
        snapshot["tag_overlap_min"] = config.tag_overlap_min
    elif config.relevance_matcher == "keyword_overlap":
        snapshot["keyword_overlap_pct"] = config.keyword_overlap_pct
    elif config.relevance_matcher == "embedding_distance":
        snapshot["embedding_distance_max"] = config.embedding_distance_max
    if config.presence_matcher == "semantic":
        snapshot["presence_semantic_threshold"] = config.presence_semantic_threshold
    return snapshot


def _write_extraction_timeout_sidecar(
    *,
    out_dir: Path,
    slug: str,
    parsed_jd: dict,
    source_board: str,
    prompt_versions: dict[str, str],
    calls: list[CallLog],
    now: datetime | None,
) -> None:
    """Write a minimal metadata sidecar after a claim-extraction timeout (AC4).

    No `claims.json` is written — AC4 explicitly forbids partial extraction
    data on disk. The package artifacts (`cv.md`, `cover-letter.md`, ...)
    are left in place so the held-package pattern (Story 3.4) can pick them
    up; the `error: "extraction_timeout"` field signals the verdict.
    """
    if not out_dir.exists():
        return
    failure_metadata = build_metadata(
        slug=slug,
        jd_source="paste",
        artifacts_produced=[],
        calls=list(calls),
        prompt_templates=prompt_versions,
        parsed_jd=parsed_jd,
        source_board=source_board,
        now=now,
        error="extraction_timeout",
    )
    write_sidecar(out_dir, failure_metadata)


# Story 6.2: drift-report Markdown sidecar -------------------------------


def _write_drift_report_markdown(out_dir: Path) -> None:
    """Render `drift-report.md` from `package.drift.json` (Story 6.2 AC2).

    The matchers above already wrote the machine-readable drift JSON; this
    step re-reads it and renders a human Markdown sidecar. Any failure
    (missing / malformed JSON) is logged at WARNING and swallowed — the
    held package itself is already on disk, and a missing Markdown sidecar
    must never break the pipeline.
    """
    drift_path = out_dir / "package.drift.json"
    try:
        drift_doc = json.loads(drift_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning(
            "drift-report writer: could not read %s: %s", drift_path, exc
        )
        return
    if not isinstance(drift_doc, dict):
        _log.warning(
            "drift-report writer: %s is not a JSON object", drift_path
        )
        return
    drift_report.write_drift_report(out_dir, drift_doc)


# Story 6.1: drift-verdict gate + post-notification sidecar rewrite -------


def _all_drift_pass(drift_verdicts: dict[str, str]) -> bool:
    """True when every required drift verdict is exactly `"pass"` (Story 6.1)."""
    return all(
        drift_verdicts.get(check) == "pass"
        for check in ("fabrication", "content_loss", "keyword_stuffing")
    )


def _notify_and_update_sidecar(
    *,
    out_dir: Path,
    package_metadata: metadata_module.PackageMetadata,
    webhook_url: str,
    now: datetime | None,
) -> metadata_module.PackageMetadata:
    """Attempt the GChat POST and re-write the sidecar with the outcome (Story 6.1).

    Wraps the notifier in try/except so any failure inside the module is
    logged at WARNING and swallowed — the pipeline still completes
    cleanly. On the happy path the metadata sidecar gains a `notification`
    block matching Story 6.1 AC3's contract (delivered or delivery_failed
    with attempts + last_error).
    """
    try:
        payload = notifier.build_payload(package_metadata, out_dir)
        result = notifier.notify(payload, webhook_url=webhook_url)
    except Exception as exc:  # noqa: BLE001 — notification is non-fatal
        _log.warning(
            "jobhunter: notifier raised %s; package at %s is on disk",
            exc,
            out_dir,
        )
        notification = {
            "status": "delivery_failed",
            "attempts": 0,
            "last_error": f"notifier_exception: {type(exc).__name__}",
        }
    else:
        if result.delivered:
            notification = {
                "status": "delivered",
                "delivered_at": metadata_module.now_iso8601_utc(now),
            }
        else:
            notification = {
                "status": "delivery_failed",
                "attempts": result.attempts,
                "last_error": result.last_error or "unknown_error",
            }

    updated = dataclasses.replace(package_metadata, notification=notification)
    write_sidecar(out_dir, updated)
    return updated
