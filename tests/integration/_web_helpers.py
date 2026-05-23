"""Shared fixtures for FastAPI web-app integration tests.

Lives outside the `test_*` discovery prefix so pytest does not collect it as a
test module. The web tests use FastAPI's `TestClient` to drive the route
handlers in-process — no subprocess, no real network, no real LLM call.
"""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from jobhunter.board_classifier import Classification
from jobhunter.config import PROJECT_ROOT
from jobhunter.jd_parser import ParsedJD
from jobhunter.llm_client import TailoringResult, UpworkProposalResult


FAKE_CV_MARKDOWN = "# Tailored CV (test stub)\n\n- Skill: pytest\n"
FAKE_COVER_LETTER_MARKDOWN = (
    "Dear hiring manager,\n\nI am a fit for this role (test stub).\n"
)
FAKE_UPWORK_PROPOSAL_MARKDOWN = (
    "I read your job description and built similar systems using pytest.\n"
)
FAKE_PROPOSAL_COST_USD = Decimal("0.002100")
FAKE_COST_USD = Decimal("0.004200")
FAKE_INPUT_TOKENS = 1234
FAKE_OUTPUT_TOKENS = 567


def make_fake_parse(
    *,
    must_haves: list[str] | None = None,
    nice_to_haves: list[str] | None = None,
    tone: str = "neutral",
    seniority: str = "senior",
    red_flags: list[str] | None = None,
    source_board: str = "unknown",
) -> Callable[..., ParsedJD]:
    def fake_parse(
        jd_text: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ParsedJD:
        return ParsedJD(
            must_haves=list(must_haves or ["Python", "FastAPI"]),
            nice_to_haves=list(nice_to_haves or ["Docker"]),
            tone=tone,
            seniority=seniority,
            red_flags=list(red_flags or []),
            raw_text_length=len(jd_text),
            source_board=source_board,
        )

    return fake_parse


def make_fake_classifier(
    *,
    source_board: str = "other",
    method: str = "heuristic",
) -> Callable[..., Classification]:
    """Stub for `board_classifier.classify_board` that honors explicit overrides."""

    def fake_classify(
        jd_text: str,
        parsed_jd: ParsedJD,
        *,
        explicit_override: str | None = None,
    ) -> Classification:
        if explicit_override is not None:
            return Classification(
                source_board=explicit_override, method="explicit_override"
            )
        return Classification(source_board=source_board, method=method)

    return fake_classify


def make_fake_tailor(
    *,
    cv: str = FAKE_CV_MARKDOWN,
    cover: str = FAKE_COVER_LETTER_MARKDOWN,
    cost: Decimal = FAKE_COST_USD,
) -> Callable[..., TailoringResult]:
    def fake_tailor(
        canonical_cv: dict[str, Any],
        jd_text: str,
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> TailoringResult:
        return TailoringResult(
            cv_markdown=cv,
            cover_letter_markdown=cover,
            cost_usd=cost,
            input_tokens=FAKE_INPUT_TOKENS,
            output_tokens=FAKE_OUTPUT_TOKENS,
        )

    return fake_tailor


def make_fake_upwork_proposal_tailor(
    *,
    proposal: str = FAKE_UPWORK_PROPOSAL_MARKDOWN,
    cost: Decimal = FAKE_PROPOSAL_COST_USD,
) -> Callable[..., UpworkProposalResult]:
    def fake_proposal_tailor(
        canonical_cv: dict[str, Any],
        jd_text: str,
        *,
        api_key: str,
        timeout_seconds: float,
        screening_questions: list[str] | None = None,
        max_words: int,
    ) -> UpworkProposalResult:
        return UpworkProposalResult(
            proposal_markdown=proposal,
            cost_usd=cost,
            input_tokens=FAKE_INPUT_TOKENS,
            output_tokens=FAKE_OUTPUT_TOKENS,
        )

    return fake_proposal_tailor


def stage_canonical_cv(tmp_path: Path, monkeypatch) -> Path:
    cv_path = tmp_path / "canonical-cv.json"
    shutil.copyfile(PROJECT_ROOT / "canonical-cv.json", cv_path)

    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def stage_tailoring(
    tmp_path: Path,
    monkeypatch,
    fake_tailor=None,
    fake_parse=None,
    fake_classify=None,
    fake_upwork_proposal_tailor=None,
):
    """Wire the FastAPI route's `run_tailoring` to write into tmp_path.

    Returns the chosen out_root / ledger_path so tests can assert on disk
    state without scanning the repo's real `./out/`.
    """
    import jobhunter.tailoring as tailoring_module
    import jobhunter.web.api as api_module

    out_root = tmp_path / "out"
    ledger_path = tmp_path / ".cost-ledger.json"
    tailor = fake_tailor or make_fake_tailor()
    parser = fake_parse or make_fake_parse()
    classifier = fake_classify
    proposal_tailor = fake_upwork_proposal_tailor or make_fake_upwork_proposal_tailor()
    original_run = tailoring_module.run_tailoring

    def patched_run(
        canonical_cv,
        jd_text,
        *,
        config,
        now=None,
        llm_tailor=None,
        llm_tailor_upwork_proposal=None,
        llm_parse=None,
        classify=None,
        source_board=None,
        artifacts_override=None,
        out_root=None,
        ledger_path=None,
    ):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now,
            llm_tailor=tailor,
            llm_tailor_upwork_proposal=proposal_tailor,
            llm_parse=parser,
            classify=classify or classifier,
            source_board=source_board,
            artifacts_override=artifacts_override,
            out_root=out_root or (tmp_path / "out"),
            ledger_path=ledger_path or (tmp_path / ".cost-ledger.json"),
        )

    monkeypatch.setattr(api_module, "run_tailoring", patched_run)
    return out_root, ledger_path


def write_ledger(ledger_path: Path, month_key: str, total: str, calls: int) -> None:
    ledger_path.write_text(
        json.dumps({month_key: {"total_usd": total, "calls": calls}}),
        encoding="utf-8",
    )
