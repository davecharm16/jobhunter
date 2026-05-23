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
    fabrication_matcher,
    held_package,
    jd_parser,
    llm_client,
    metadata as metadata_module,
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

    # Story 3.4 AC1 + AC2: on fabrication=fail, write `package.held.json` and
    # record `held=true` + `held_path` on the metadata sidecar. The held-
    # package writer is the ONLY post-matcher branch — there is no
    # notification call here, structurally enforcing the no-notify contract
    # (AC2). Notifications land in Epic 6.
    held_path_value: str | None = None
    if fabrication_check.verdict == "fail":
        held_path_value = _run_held_package_writer(
            out_dir=out_dir,
            unsourced_claims=fabrication_check.unsourced_claims,
            now=now,
        )

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
    now: datetime | None,
) -> str:
    """Compose + atomically write `package.held.json`; return its path string (Story 3.4 AC1)."""
    retention_days = _resolve_held_retention_days()
    moment = now or datetime.now(timezone.utc)
    record = held_package.compose_held_record(
        unsourced_claims,
        out_dir,
        now=moment,
        retention_days=retention_days,
    )
    held_path = held_package.write_held_sidecar(out_dir, record)
    return str(held_path)


def _run_held_sweep(root: Path, *, now: datetime | None) -> None:
    """Sweep expired held packages off disk; best-effort (Story 3.4 AC3).

    Invoked at the top of `run_tailoring` before any LLM work. Any failure
    is logged at WARNING and swallowed — the sweep must never abort the
    pipeline that just started running.
    """
    try:
        retention_days = _resolve_held_retention_days()
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
    """Pull `fabrication.held_retention_days` from `config.yaml` (default 7)."""
    try:
        yaml = yaml_config.load_yaml_config()
    except yaml_config.YamlConfigError:
        return 7
    return int(yaml.fabrication.held_retention_days)


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
