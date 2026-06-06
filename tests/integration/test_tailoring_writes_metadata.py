"""Story 2.10 integration: run_tailoring writes metadata.json next to artifacts.

Covers AC1 (full payload shape), AC2 (per-call log entry), AC3 (total +
per-app target + breach flag), AC4 (pre-call cap check still in path —
SpendCapExceeded short-circuits before any artifact or metadata is written),
and AC5 (atomic write — no `.metadata.tmp` left on disk after success).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from jobhunter.llm_client import MODEL_NAME, TailoringResult
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.spend_tracker import SpendCapExceeded
from jobhunter.tailoring import run_tailoring


FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)


def _config() -> RuntimeConfig:
    return RuntimeConfig(
        llm_api_key="test-key",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )


def _fake_tailor_factory(
    *,
    cost: Decimal = Decimal("0.004200"),
    input_tokens: int = 1234,
    output_tokens: int = 567,
    cv: str = "# CV\n",
    cover: str = "Dear hiring manager,\n",
):
    def fake_tailor(
        canonical_cv,
        jd_text,
        *,
        api_key,
        timeout_seconds,
    ):
        return TailoringResult(
            cv_markdown=cv,
            cover_letter_markdown=cover,
            cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    return fake_tailor


def _zero_cost_extractor(
    markdown_text, source_artifact, *, api_key, timeout_seconds, prompt,
):
    """Story 3.1: zero-cost extractor for tests that pin pre-Story-3.1 cost totals.

    The integration-conftest autouse stub charges $0.000050 per call, which
    would push these AC3 totals off the pre-Story-3.1 snapshot. Tests that
    specifically assert the tailor-only cost inject this stub to neutralize
    the extraction calls.
    """
    from jobhunter.claim_extractor import ClaimExtractionResult

    return ClaimExtractionResult(
        claims=[], cost_usd=Decimal("0"), input_tokens=0, output_tokens=0,
    )


# --- AC1: metadata.json with full structured payload ---------------------


def test_run_tailoring_writes_metadata_json_with_full_ac1_payload(tmp_path) -> None:
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    metadata_path = outcome.out_dir / "metadata.json"
    assert metadata_path.exists()
    data = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert data["slug"] == outcome.out_dir.name
    # Story 2.4 wires the source-board classifier into run_tailoring; a JD with
    # no Upwork/OJ.ph/LinkedIn signal resolves to "other" (was placeholder
    # "unknown" before Story 2.4 landed).
    assert data["source_board"] == "other"
    assert data["jd_source"] == "paste"
    # Story 2.3 populates parsed_jd; the test asserts the shape exists rather
    # than the exact contents (the autouse parse stub supplies deterministic
    # values; see tests/integration/conftest.py).
    assert isinstance(data["parsed_jd"], dict)
    assert "must_haves" in data["parsed_jd"]
    assert data["red_flags"] == []
    assert data["artifacts_produced"] == ["cv", "cover_letter"]
    # Story 3.1 adds `claims_extract` to the prompt-versions surface.
    assert data["prompt_templates"] == {
        "cv": "v1",
        "cover_letter": "v1",
        "claims_extract": "v1",
    }
    # Story 3.2: the structural fabrication matcher runs after claim
    # extraction and overrides `fabrication` from "pending" to a real verdict.
    # This test's canonical CV is `{"basics": {"name": "X"}}` (no work, skills,
    # projects, or education), so the autouse stub's `pytest` claim has no
    # canonical source -> verdict is "fail".
    # Story 4.1: `content_loss` is now overridden by the content-loss matcher;
    # with no high-impact entries in the canonical CV the must-appear set is
    # empty and the verdict is `pass`.
    # Story 5.1: `keyword_stuffing` is now overridden by the density matcher.
    # The autouse `_stub_llm_parse_jd` fixture returns must_haves=["Python"];
    # the FAKE_CV_MARKDOWN body is short, so 0 occurrences of "Python" -> pass.
    assert data["drift_verdicts"] == {
        "fabrication": "fail",
        "content_loss": "pass",
        "keyword_stuffing": "pass",
    }
    assert data["override"] == {"applied": False, "reason": None}
    assert data["created_at"] == "2026-05-24T03:15:30Z"
    assert "cost" in data


# --- AC2: per-call log entry captures model, tokens, usd_cost, purpose ---


def test_run_tailoring_appends_tailoring_call_to_cost_calls(tmp_path) -> None:
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(
            cost=Decimal("0.004200"),
            input_tokens=1234,
            output_tokens=567,
        ),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    data = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    # Story 3.1: the tailoring call is followed by per-artifact extract_claims
    # calls (one per produced artifact); the test pins the tailoring entry
    # specifically and asserts the extract_claims tail separately.
    tail_purposes = [c["purpose"] for c in data["cost"]["calls"][1:]]
    assert data["cost"]["calls"][0] == {
        "model": MODEL_NAME,
        "input_tokens": 1234,
        "output_tokens": 567,
        "usd_cost": "0.004200",
        "purpose": "tailor_cv_and_cover_letter",
    }
    assert tail_purposes == ["extract_claims", "extract_claims"]


# --- AC3: total + per-app target visible ----------------------------------


def test_run_tailoring_writes_total_and_target_below_cap(tmp_path) -> None:
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(cost=Decimal("0.020000")),
        llm_extract_claims=_zero_cost_extractor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    data = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    # Story 3.1: injected extractor returns $0 so the total still pins.
    assert data["cost"]["total_usd"] == "0.020000"
    assert data["cost"]["per_app_target_usd"] == "0.250000"
    assert data["cost"]["exceeded_per_app_target"] is False


def test_run_tailoring_flags_exceeded_per_app_target(tmp_path) -> None:
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(cost=Decimal("0.500000")),
        llm_extract_claims=_zero_cost_extractor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    data = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert data["cost"]["total_usd"] == "0.500000"
    assert data["cost"]["exceeded_per_app_target"] is True


# --- AC4: pre-call cap check still short-circuits ------------------------


def test_run_tailoring_cap_exceeded_writes_no_metadata(tmp_path) -> None:
    """SpendCapExceeded must short-circuit before any artifact or metadata is
    written. NFR15: pre-call cap check is non-bypassable.
    """
    out_root = tmp_path / "out"
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({"2026-05": {"total_usd": "25.00", "calls": 999}}),
        encoding="utf-8",
    )

    def must_not_run(*args, **kwargs):
        raise AssertionError("LLM must not be invoked when cap is reached")

    with pytest.raises(SpendCapExceeded):
        run_tailoring(
            {"basics": {"name": "X"}},
            "Senior Python role.\n",
            config=_config(),
            now=FIXED_NOW,
            llm_tailor=must_not_run,
            out_root=out_root,
            ledger_path=ledger_path,
        )

    assert not out_root.exists()


# --- AC5: atomic write — no .metadata.tmp left behind --------------------


def test_run_tailoring_leaves_no_metadata_tmp_after_success(tmp_path) -> None:
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert (outcome.out_dir / "metadata.json").exists()
    assert not (outcome.out_dir / ".metadata.tmp").exists()


def test_run_tailoring_metadata_sits_next_to_artifacts(tmp_path) -> None:
    """All three files land in the same `./out/<slug>/` directory."""
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    files = {p.name for p in outcome.out_dir.iterdir()}
    # Story 3.1 adds claims.json next to the tailored artifacts.
    # Story 3.2 adds package.drift.json next to claims.json.
    # Story 3.4: the minimal canonical CV used by this test has no
    # `pytest` source entry, so the stub claim emitted by the autouse
    # extractor in `tests/integration/conftest.py` is unsourced and the
    # fabrication matcher emits a `fail` verdict — which now writes
    # `package.held.json` next to the existing artifacts.
    # Story 4.1: `tailoring.trace.json` lands next to the existing artifacts
    # as the (initially empty) explicit-omission rationale log consumed by
    # the content-loss check.
    # Story 6.2 AC2: a human-readable `drift-report.md` is written whenever
    # any drift check fails (the same condition that produces `package.held.json`).
    # The minimal CV used by this test still triggers a fabrication fail so
    # the report sidecar also lands here.
    # Regenerate feature: the raw JD text is persisted as `jd.txt` so a held
    # package can be re-tailored with author correction notes against the same JD.
    assert files == {
        "cv.md",
        "cover-letter.md",
        "claims.json",
        "package.drift.json",
        "package.held.json",
        "tailoring.trace.json",
        "metadata.json",
        "drift-report.md",
        "jd.txt",
    }
