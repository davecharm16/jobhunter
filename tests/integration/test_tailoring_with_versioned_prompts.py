"""Integration tests: `run_tailoring` consumes versioned prompts (Story 2.9).

Covers AC3 (versions surface on `TailoringOutcome`, real `tailor()` receives
the `PromptTemplate` map) and AC4 (missing template fails before the cap
check, and before any LLM call).
"""

from __future__ import annotations

import json
from datetime import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from jobhunter.llm_client import TailoringResult
from jobhunter.prompts import PromptTemplateMissing
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.tailoring import TailoringOutcome, run_tailoring

_CV_PAYLOAD = "system prompt for cv v7\n"
_COVER_PAYLOAD = "system prompt for cover letter v4\n"


def _make_config() -> RuntimeConfig:
    return RuntimeConfig(
        llm_api_key="test-key",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )


def _stage_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cv_version: int = 1,
    cover_version: int = 1,
    cv_content: str = _CV_PAYLOAD,
    cover_content: str = _COVER_PAYLOAD,
    skip_cv: bool = False,
    skip_cover: bool = False,
) -> Path:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    if not skip_cv:
        (prompts_dir / f"cv.v{cv_version}.md").write_text(
            cv_content, encoding="utf-8"
        )
    if not skip_cover:
        (prompts_dir / f"cover_letter.v{cover_version}.md").write_text(
            cover_content, encoding="utf-8"
        )
    import jobhunter.prompts as prompts_module

    monkeypatch.setattr(prompts_module, "PROMPTS_DIR", prompts_dir)
    return prompts_dir


def _happy_tailor_factory(
    captured: dict[str, Any],
) -> Any:
    """Build a `client_factory` that records what `tailor()` sent the SDK."""

    class _FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            captured["create_kwargs"] = kwargs

            class _Block:
                type = "tool_use"
                input = {
                    "cv_markdown": "# CV\n",
                    "cover_letter_markdown": "Dear team\n",
                }

            class _Usage:
                input_tokens = 10
                output_tokens = 5

            class _Response:
                content = [_Block()]
                usage = _Usage()

            return _Response()

    class _FakeClient:
        def __init__(self, *, api_key: str, timeout: float) -> None:
            self.api_key = api_key
            self.timeout = timeout
            self.messages = _FakeMessages()

    def factory(*, api_key: str, timeout: float) -> _FakeClient:
        return _FakeClient(api_key=api_key, timeout=timeout)

    return factory


# --- AC3: prompt_versions surfaces on the outcome --------------------------


def test_run_tailoring_surfaces_prompt_versions_on_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_prompts(tmp_path, monkeypatch, cv_version=3, cover_version=2)

    def fake_tailor(canonical_cv, jd_text, **kwargs):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_make_config(),
        llm_tailor=fake_tailor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert isinstance(outcome, TailoringOutcome)
    # Story 3.1: `claims_extract` joins the prompt-version surface.
    assert outcome.prompt_versions == {
        "cv": "v3", "cover_letter": "v2", "claims_extract": "v1",
    }


def test_run_tailoring_picks_highest_version_per_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "cv.v1.md").write_text("v1\n", encoding="utf-8")
    (prompts_dir / "cv.v5.md").write_text("v5\n", encoding="utf-8")
    (prompts_dir / "cover_letter.v1.md").write_text("v1\n", encoding="utf-8")
    import jobhunter.prompts as prompts_module

    monkeypatch.setattr(prompts_module, "PROMPTS_DIR", prompts_dir)

    def fake_tailor(canonical_cv, jd_text, **kwargs):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "JD\n",
        config=_make_config(),
        llm_tailor=fake_tailor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert outcome.prompt_versions["cv"] == "v5"
    assert outcome.prompt_versions["cover_letter"] == "v1"


# --- AC3: real tailor() receives the PromptTemplate map -------------------


def test_real_tailor_uses_prompt_template_content_as_system_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `run_tailoring` calls the real `llm_client.tailor`, the loaded
    cv template's content becomes the SDK's `system=` argument."""
    _stage_prompts(
        tmp_path,
        monkeypatch,
        cv_version=2,
        cover_version=2,
        cv_content="CUSTOM CV SYSTEM PROMPT v2\n",
        cover_content="CUSTOM COVER LETTER PROMPT v2\n",
    )

    captured: dict[str, Any] = {}
    factory = _happy_tailor_factory(captured)

    import jobhunter.llm_client as llm_module
    from jobhunter.llm_client import tailor as real_tailor

    def production_path_tailor(*args, **kwargs):
        kwargs.setdefault("client_factory", factory)
        return real_tailor(*args, **kwargs)

    monkeypatch.setattr(llm_module, "tailor", production_path_tailor)

    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_make_config(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    # Story 3.1: `claims_extract` joins the prompt-version surface.
    assert outcome.prompt_versions == {
        "cv": "v2", "cover_letter": "v2", "claims_extract": "v1",
    }
    assert captured["create_kwargs"]["system"] == "CUSTOM CV SYSTEM PROMPT v2\n"


# --- AC4: missing template fails BEFORE any LLM call ----------------------


def test_run_tailoring_raises_when_cv_template_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_prompts(tmp_path, monkeypatch, skip_cv=True)

    invoked = {"called": False}

    def must_not_run(*args, **kwargs):
        invoked["called"] = True
        raise AssertionError("LLM tailor must not run when prompt is missing")

    with pytest.raises(PromptTemplateMissing, match="cv"):
        run_tailoring(
            {"basics": {"name": "X"}},
            "JD\n",
            config=_make_config(),
            llm_tailor=must_not_run,
            out_root=tmp_path / "out",
            ledger_path=tmp_path / ".cost-ledger.json",
        )
    assert invoked["called"] is False


def test_run_tailoring_raises_when_cover_letter_template_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_prompts(tmp_path, monkeypatch, skip_cover=True)

    invoked = {"called": False}

    def must_not_run(*args, **kwargs):
        invoked["called"] = True
        raise AssertionError("LLM tailor must not run when prompt is missing")

    with pytest.raises(PromptTemplateMissing, match="cover_letter"):
        run_tailoring(
            {"basics": {"name": "X"}},
            "JD\n",
            config=_make_config(),
            llm_tailor=must_not_run,
            out_root=tmp_path / "out",
            ledger_path=tmp_path / ".cost-ledger.json",
        )
    assert invoked["called"] is False


def test_run_tailoring_raises_when_prompts_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jobhunter.prompts as prompts_module

    monkeypatch.setattr(
        prompts_module, "PROMPTS_DIR", tmp_path / "does-not-exist"
    )

    invoked = {"called": False}

    def must_not_run(*args, **kwargs):
        invoked["called"] = True
        raise AssertionError("LLM tailor must not run")

    with pytest.raises(PromptTemplateMissing):
        run_tailoring(
            {"basics": {"name": "X"}},
            "JD\n",
            config=_make_config(),
            llm_tailor=must_not_run,
            out_root=tmp_path / "out",
            ledger_path=tmp_path / ".cost-ledger.json",
        )
    assert invoked["called"] is False


# --- AC4: missing template fails BEFORE the cap check ---------------------


def test_run_tailoring_template_check_runs_before_cap_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the cap is already exhausted AND the prompt is missing, the
    template-missing error fires first — the cap check is downstream of
    template loading in `run_tailoring`'s ordering."""
    _stage_prompts(tmp_path, monkeypatch, skip_cv=True)

    # Pre-populate the ledger with spend equal to the cap so a cap-check
    # would otherwise raise.
    from datetime import datetime

    ledger_path = tmp_path / ".cost-ledger.json"
    month_key = datetime.now(UTC).strftime("%Y-%m")
    ledger_path.write_text(
        json.dumps(
            {month_key: {"total_usd": "25.00", "calls": 99}}
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromptTemplateMissing):
        run_tailoring(
            {"basics": {"name": "X"}},
            "JD\n",
            config=_make_config(),
            out_root=tmp_path / "out",
            ledger_path=ledger_path,
        )


# --- AC4: error message names the missing path ----------------------------


def test_missing_template_error_names_the_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_prompts(tmp_path, monkeypatch, skip_cv=True)

    with pytest.raises(PromptTemplateMissing) as excinfo:
        run_tailoring(
            {"basics": {"name": "X"}},
            "JD\n",
            config=_make_config(),
            out_root=tmp_path / "out",
            ledger_path=tmp_path / ".cost-ledger.json",
        )
    assert "cv" in str(excinfo.value)
