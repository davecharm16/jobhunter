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
    assert data["source_board"] == "unknown"
    assert data["jd_source"] == "paste"
    assert data["parsed_jd"] == {}
    assert data["red_flags"] == []
    assert data["artifacts_produced"] == ["cv", "cover_letter"]
    assert data["prompt_templates"] == {}
    assert data["drift_verdicts"] == {
        "fabrication": "pending",
        "content_loss": "pending",
        "keyword_stuffing": "pending",
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
    assert data["cost"]["calls"] == [
        {
            "model": MODEL_NAME,
            "input_tokens": 1234,
            "output_tokens": 567,
            "usd_cost": "0.004200",
            "purpose": "tailor_cv_and_cover_letter",
        }
    ]


# --- AC3: total + per-app target visible ----------------------------------


def test_run_tailoring_writes_total_and_target_below_cap(tmp_path) -> None:
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor_factory(cost=Decimal("0.020000")),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    data = json.loads(
        (outcome.out_dir / "metadata.json").read_text(encoding="utf-8")
    )
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
    assert files == {"cv.md", "cover-letter.md", "metadata.json"}
