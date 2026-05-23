"""Integration: Upwork proposal generation wired into POST /api/paste (Story 2.7).

Covers all four AC groups:
- AC1: versioned `upwork_proposal.v{N}.md` template loaded and recorded in
  metadata.prompt_templates; proposal generated through a distinct callable.
- AC2: `proposal.max_words` cap enforced; over-length raises, writes a
  failure sidecar with `error="over_length"`, and produces no proposal file.
- AC3: screening questions are plumbed into the proposal call; absent
  keywords surface as WARNING log lines (not fatal).
- AC4: a second `CallLog` is appended (`purpose="tailor_upwork_proposal"`);
  the per-call cap check fires between the two LLM calls; a cap breach
  there raises `SpendCapExceeded` and no proposal is generated.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.jd_parser import ParsedJD
from jobhunter.llm_client import (
    LLMCallFailed,
    TailoringResult,
    UpworkProposalOverLength,
    UpworkProposalResult,
)
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.spend_tracker import SpendCapExceeded
from jobhunter.tailoring import run_tailoring
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    FAKE_PROPOSAL_COST_USD,
    FAKE_UPWORK_PROPOSAL_MARKDOWN,
    make_fake_classifier,
    make_fake_parse,
    make_fake_upwork_proposal_tailor,
    stage_canonical_cv,
    stage_tailoring,
    write_ledger,
)


_FIXED_NOW = None  # tests use real wall clock for slug generation


def _read_metadata(out_root: Path) -> dict:
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1, slug_dirs
    return json.loads((slug_dirs[0] / "metadata.json").read_text(encoding="utf-8"))


# --- AC1: versioned template + distinct generation path -------------------


def test_upwork_pipeline_writes_upwork_proposal_md(tmp_path, monkeypatch) -> None:
    """An upwork-classified JD produces `upwork-proposal.md` alongside CV + cover letter."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    proposal_path = slug_dir / "upwork-proposal.md"
    assert proposal_path.exists()
    assert proposal_path.read_text(encoding="utf-8") == FAKE_UPWORK_PROPOSAL_MARKDOWN


def test_paste_response_surfaces_upwork_proposal_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upwork_proposal_path"] is not None
    assert body["upwork_proposal_path"].endswith("upwork-proposal.md")


def test_non_upwork_pipeline_does_not_write_upwork_proposal_md(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role at Acme.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    slug_dir = slug_dirs[0]
    assert not (slug_dir / "upwork-proposal.md").exists()
    body = response.json()
    assert body["upwork_proposal_path"] is None


def test_metadata_prompt_templates_includes_upwork_proposal_version(
    tmp_path, monkeypatch,
) -> None:
    """`metadata.prompt_templates["upwork_proposal"]` is populated for upwork."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert "upwork_proposal" in metadata["prompt_templates"]
    assert metadata["prompt_templates"]["upwork_proposal"].startswith("v")
    assert "cv" in metadata["prompt_templates"]


# --- AC2: length-bounded; over-length fails cleanly -----------------------


def _make_overlength_proposal_tailor():
    long_text = " ".join(["word"] * 500)  # 500 words

    def fake(
        canonical_cv, jd_text, *, api_key, timeout_seconds,
        screening_questions=None, max_words,
    ):
        return UpworkProposalResult(
            proposal_markdown=long_text,
            cost_usd=Decimal("0.001"),
            input_tokens=10,
            output_tokens=10,
        )

    return fake


def test_overlength_proposal_raises_and_writes_error_sidecar(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_upwork_proposal_tailor=_make_overlength_proposal_tailor(),
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "upwork_proposal_over_length"
    assert detail["max_words"] == 250
    assert detail["word_count"] == 500

    # Failure sidecar present; no proposal file on disk; cv/cover-letter not landed.
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    assert not (slug_dir / "upwork-proposal.md").exists()
    assert not (slug_dir / "cv.md").exists()
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["error"] == "over_length"
    # Both calls were billed and recorded before the over-length verdict.
    purposes = [c["purpose"] for c in metadata["cost"]["calls"]]
    assert "tailor_cv_and_cover_letter" in purposes
    assert "tailor_upwork_proposal" in purposes


def test_proposal_at_cap_passes(tmp_path, monkeypatch) -> None:
    exactly_at_cap = " ".join(["word"] * 250)

    def fake(
        canonical_cv, jd_text, *, api_key, timeout_seconds,
        screening_questions=None, max_words,
    ):
        return UpworkProposalResult(
            proposal_markdown=exactly_at_cap,
            cost_usd=Decimal("0.001"),
            input_tokens=10,
            output_tokens=10,
        )

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path, monkeypatch, fake_upwork_proposal_tailor=fake,
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text


# --- AC3: screening questions plumbed through and smoke-checked -----------


def test_screening_questions_reach_proposal_tailor(tmp_path) -> None:
    captured: dict = {}

    def capturing_proposal_tailor(
        canonical_cv, jd_text, *, api_key, timeout_seconds,
        screening_questions=None, max_words,
    ):
        captured["screening_questions"] = list(screening_questions or [])
        captured["max_words"] = max_words
        return UpworkProposalResult(
            proposal_markdown="I have years of Python experience and can start soon.\n",
            cost_usd=Decimal("0.001"),
            input_tokens=10,
            output_tokens=10,
        )

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    jd = (
        "Posted on upwork.com.\n"
        "Budget: $50/hr.\n\n"
        "Screening Questions:\n"
        "1. How many years of Python?\n"
        "2. Can you start within two weeks?\n"
    )
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        jd,
        config=config,
        llm_tailor=fake_tailor,
        llm_tailor_upwork_proposal=capturing_proposal_tailor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    assert outcome.upwork_proposal_path is not None
    assert captured["screening_questions"] == [
        "How many years of Python?",
        "Can you start within two weeks?",
    ]
    assert captured["max_words"] == 250


def test_missing_screening_keyword_emits_warning(
    tmp_path, caplog,
) -> None:
    def stub_proposal_tailor(
        canonical_cv, jd_text, *, api_key, timeout_seconds,
        screening_questions=None, max_words,
    ):
        # Deliberately omit "kubernetes" so the keyword is absent.
        return UpworkProposalResult(
            proposal_markdown="I have Python experience and can start within two weeks.\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    jd = (
        "Posted on upwork.com.\n\n"
        "Screening Questions:\n"
        "1. Have you used Kubernetes in production?\n"
    )
    with caplog.at_level(logging.WARNING, logger="jobhunter.tailoring"):
        run_tailoring(
            {"basics": {"name": "X"}},
            jd,
            config=config,
            llm_tailor=fake_tailor,
            llm_tailor_upwork_proposal=stub_proposal_tailor,
            out_root=tmp_path / "out",
            ledger_path=tmp_path / ".cost-ledger.json",
        )
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Kubernetes" in r.getMessage() for r in warnings), warnings


def test_present_screening_keywords_emit_no_warning(
    tmp_path, caplog,
) -> None:
    def stub_proposal_tailor(
        canonical_cv, jd_text, *, api_key, timeout_seconds,
        screening_questions=None, max_words,
    ):
        return UpworkProposalResult(
            proposal_markdown="I have hands-on Python and FastAPI production experience.\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    jd = (
        "Posted on upwork.com.\n\n"
        "Screening Questions:\n"
        "1. Have you used Python in production?\n"
        "2. Have you used FastAPI?\n"
    )
    with caplog.at_level(logging.WARNING, logger="jobhunter.tailoring"):
        run_tailoring(
            {"basics": {"name": "X"}},
            jd,
            config=config,
            llm_tailor=fake_tailor,
            llm_tailor_upwork_proposal=stub_proposal_tailor,
            out_root=tmp_path / "out",
            ledger_path=tmp_path / ".cost-ledger.json",
        )
    smoke_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "smoke check" in r.getMessage()
    ]
    assert smoke_warnings == [], smoke_warnings


# --- AC4: cost contribution + monthly cap honored --------------------------


def test_metadata_records_two_call_logs_with_distinct_purposes(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    purposes = [c["purpose"] for c in metadata["cost"]["calls"]]
    # Story 3.1: extract_claims runs per artifact in `artifacts_produced`
    # (upwork board ships {cv, upwork_proposal}, so two extraction calls).
    assert purposes == [
        "tailor_cv_and_cover_letter",
        "tailor_upwork_proposal",
        "extract_claims",
        "extract_claims",
    ]


def test_total_cost_sums_both_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    total = Decimal(metadata["cost"]["total_usd"])
    per_call = sum(
        (Decimal(c["usd_cost"]) for c in metadata["cost"]["calls"]),
        Decimal("0"),
    )
    assert total == per_call


def test_cap_breach_between_calls_aborts_proposal_call(
    tmp_path, monkeypatch,
) -> None:
    """If cv-letter call lifts spend over the cap, the proposal call is refused."""
    from datetime import datetime, timezone

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    # Pre-seed the ledger so the FIRST cap check passes (current < cap), but
    # the FIRST tailor call's recorded spend lifts the ledger total to/over
    # the cap. The SECOND cap check (before the proposal LLM call) then
    # fires and raises. The default fake tailor records $0.004200, so
    # 24.9960 + 0.004200 = 25.0002 > 25.00.
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger_path = tmp_path / ".cost-ledger.json"
    write_ledger(ledger_path, month_key, "24.9960", 100)

    proposal_invocations = {"count": 0}

    def must_not_run_proposal(*args, **kwargs):
        proposal_invocations["count"] += 1
        raise AssertionError(
            "proposal_tailor must not run once monthly cap is reached"
        )

    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_upwork_proposal_tailor=must_not_run_proposal,
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 402, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "monthly_spend_cap_reached"
    assert proposal_invocations["count"] == 0
    # tmp_dir was cleaned up; no slug dir landed on disk.
    if out_root.exists():
        slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
        assert slug_dirs == []


def test_paste_proposal_llm_failure_returns_502(tmp_path, monkeypatch) -> None:
    """LLM provider error during the proposal call surfaces as a 502."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise LLMCallFailed("provider returned 503")

    out_root, _ = stage_tailoring(
        tmp_path, monkeypatch, fake_upwork_proposal_tailor=boom,
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 502
    assert "LLM call failed" in response.json()["detail"]
    # Failed mid-pipeline; tmp cleaned up, no partial slug dirs.
    if out_root.exists():
        slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
        assert slug_dirs == []


# --- run_tailoring direct: TailoringOutcome carries the new field ---------


def test_run_tailoring_outcome_exposes_upwork_proposal_path(tmp_path) -> None:
    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Posted on upwork.com.\n",
        config=config,
        llm_tailor=fake_tailor,
        llm_tailor_upwork_proposal=make_fake_upwork_proposal_tailor(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert outcome.upwork_proposal_path is not None
    assert outcome.upwork_proposal_path.endswith("upwork-proposal.md")
    assert Path(outcome.upwork_proposal_path).exists()


def test_run_tailoring_outcome_proposal_path_none_for_non_upwork(tmp_path) -> None:
    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role at Acme.\n",
        config=config,
        llm_tailor=fake_tailor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert outcome.upwork_proposal_path is None


# --- AC1 (artifact files): atomic write across all three artifacts --------


def test_failing_proposal_call_leaves_no_partial_package(
    tmp_path, monkeypatch,
) -> None:
    """If the proposal call fails AFTER cv+cover-letter ran, nothing ships."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise LLMCallFailed("provider returned 503")

    out_root, _ = stage_tailoring(
        tmp_path, monkeypatch, fake_upwork_proposal_tailor=boom,
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 502
    if out_root.exists():
        slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
        assert slug_dirs == []
