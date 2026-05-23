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

from jobhunter.config import PROJECT_ROOT
from jobhunter.llm_client import TailoringResult


FAKE_CV_MARKDOWN = "# Tailored CV (test stub)\n\n- Skill: pytest\n"
FAKE_COVER_LETTER_MARKDOWN = (
    "Dear hiring manager,\n\nI am a fit for this role (test stub).\n"
)
FAKE_COST_USD = Decimal("0.004200")
FAKE_INPUT_TOKENS = 1234
FAKE_OUTPUT_TOKENS = 567


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


def stage_canonical_cv(tmp_path: Path, monkeypatch) -> Path:
    cv_path = tmp_path / "canonical-cv.json"
    shutil.copyfile(PROJECT_ROOT / "canonical-cv.json", cv_path)

    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def stage_tailoring(tmp_path: Path, monkeypatch, fake_tailor=None):
    """Wire the FastAPI route's `run_tailoring` to write into tmp_path.

    Returns the chosen out_root / ledger_path so tests can assert on disk
    state without scanning the repo's real `./out/`.
    """
    import jobhunter.tailoring as tailoring_module
    import jobhunter.web.api as api_module

    out_root = tmp_path / "out"
    ledger_path = tmp_path / ".cost-ledger.json"
    tailor = fake_tailor or make_fake_tailor()
    original_run = tailoring_module.run_tailoring

    def patched_run(
        canonical_cv,
        jd_text,
        *,
        config,
        now=None,
        llm_tailor=None,
        out_root=None,
        ledger_path=None,
    ):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now,
            llm_tailor=tailor,
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
