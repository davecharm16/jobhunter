"""Integration: OJ.ph signal extractor wired into `run_tailoring` (Story 2.6).

Covers AC1 (extractor runs when `source_board == "onlinejobs_ph"` and
populates `parsed.signals["onlinejobs_ph"]`), AC2 (rate-below-floor red flag
appended to `parsed.red_flags` and surfaced in metadata's `parsed_jd.red_flags`),
and the gating invariant (extractor does NOT run for other source boards).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from jobhunter.board_classifier import Classification
from jobhunter.jd_parser import ParsedJD
from jobhunter.llm_client import TailoringResult
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.tailoring import run_tailoring


FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)


def _config() -> RuntimeConfig:
    return RuntimeConfig(
        llm_api_key="test-key",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )


def _fake_tailor(
    canonical_cv,
    jd_text,
    *,
    api_key,
    timeout_seconds,
):
    return TailoringResult(
        cv_markdown="# CV\n",
        cover_letter_markdown="Dear hiring manager,\n",
        cost_usd=Decimal("0.004200"),
        input_tokens=100,
        output_tokens=50,
    )


def _parse_factory(*, red_flags: list[str] | None = None):
    """Build a fake `jd_parser.parse_jd` that returns a fresh ParsedJD.

    A fresh object is returned per call so the orchestrator's mutation of
    `signals` / `red_flags` does not bleed between tests.
    """

    def fake_parse(jd_text, *, api_key, timeout_seconds, prompt):
        return ParsedJD(
            must_haves=["Python"],
            nice_to_haves=["Docker"],
            tone="neutral",
            seniority="senior",
            red_flags=list(red_flags or []),
            raw_text_length=len(jd_text),
        )

    return fake_parse


def _force_classification(source_board: str):
    def fake_classify(jd_text, parsed_jd, *, explicit_override=None):
        return Classification(source_board=source_board, method="heuristic")

    return fake_classify


# --- AC1: signals populated when source_board is onlinejobs_ph -----------


def test_signals_populated_for_onlinejobs_ph_source_board(tmp_path) -> None:
    """OJ.ph JD with a $1000/month rate populates `parsed.signals['onlinejobs_ph']`."""
    captured: dict = {}

    def capturing_parse(jd_text, *, api_key, timeout_seconds, prompt):
        parsed = _parse_factory()(
            jd_text, api_key=api_key, timeout_seconds=timeout_seconds, prompt=prompt
        )
        captured["parsed"] = parsed
        return parsed

    run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA role, monthly rate: $1000.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=capturing_parse,
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    signals = captured["parsed"].signals["onlinejobs_ph"]
    assert signals["rate_range"] == {
        "min": 1000,
        "max": 1000,
        "currency": "USD",
        "period": "monthly",
    }
    assert signals["role_type"] == "full_time"


def test_signals_missing_fields_are_none(tmp_path) -> None:
    """A JD with no rate or role-type yields `None` fields — never fabricated."""
    captured: dict = {}

    def capturing_parse(jd_text, *, api_key, timeout_seconds, prompt):
        parsed = _parse_factory()(
            jd_text, api_key=api_key, timeout_seconds=timeout_seconds, prompt=prompt
        )
        captured["parsed"] = parsed
        return parsed

    run_tailoring(
        {"basics": {"name": "X"}},
        "Looking for a VA. Apply via our site.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=capturing_parse,
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    signals = captured["parsed"].signals["onlinejobs_ph"]
    assert signals["rate_range"] is None
    assert signals["role_type"] is None


# --- AC2: rate-below-floor red flag --------------------------------------


def test_rate_below_floor_red_flag_appended_for_low_usd_rate(tmp_path) -> None:
    """A $400/month USD rate falls below the 600 floor and is flagged."""
    out_root = tmp_path / "out"
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA, monthly rate: $400.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=_parse_factory(),
        classify=_force_classification("onlinejobs_ph"),
        out_root=out_root,
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "rate_below_floor" in data["parsed_jd"]["red_flags"]


def test_rate_at_or_above_floor_does_not_trigger_red_flag(tmp_path) -> None:
    """A $1000/month USD rate is above the 600 floor; no red flag added."""
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA, monthly rate: $1000.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=_parse_factory(),
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "rate_below_floor" not in data["parsed_jd"]["red_flags"]


def test_php_rate_below_floor_after_conversion_triggers_red_flag(tmp_path) -> None:
    """PHP 20,000/month converts to ~$357 USD — below the 600 floor, flagged."""
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA, PHP 20,000 monthly.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=_parse_factory(),
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "rate_below_floor" in data["parsed_jd"]["red_flags"]


def test_php_rate_above_floor_after_conversion_does_not_flag(tmp_path) -> None:
    """PHP 50,000/month converts to ~$892 USD — above the 600 floor."""
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA, PHP 50,000 monthly.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=_parse_factory(),
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "rate_below_floor" not in data["parsed_jd"]["red_flags"]


def test_no_rate_in_jd_does_not_add_red_flag(tmp_path) -> None:
    """Missing rate must not fabricate a red flag (AC1: never fabricate)."""
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA role.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=_parse_factory(),
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "rate_below_floor" not in data["parsed_jd"]["red_flags"]


# --- Gating: extractor must NOT run for other source boards --------------


def test_extractor_skipped_for_non_onlinejobs_ph_board(tmp_path) -> None:
    """An Upwork-classified JD with an OJ.ph-style rate must not get OJ.ph signals."""
    captured: dict = {}

    def capturing_parse(jd_text, *, api_key, timeout_seconds, prompt):
        parsed = _parse_factory()(
            jd_text, api_key=api_key, timeout_seconds=timeout_seconds, prompt=prompt
        )
        captured["parsed"] = parsed
        return parsed

    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time role, monthly rate: $400.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=capturing_parse,
        classify=_force_classification("upwork"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    assert "onlinejobs_ph" not in captured["parsed"].signals
    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert "rate_below_floor" not in data["parsed_jd"]["red_flags"]


# --- AC3 bridge: extractor does not interfere with the metadata sidecar --


def test_extractor_preserves_parsed_jd_metadata_shape(tmp_path) -> None:
    """Signals are kept off `parsed_jd` so Story 2.3's 6-field contract holds."""
    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Full-time VA, monthly rate: $1000.\n",
        config=_config(),
        now=FIXED_NOW,
        llm_tailor=_fake_tailor,
        llm_parse=_parse_factory(),
        classify=_force_classification("onlinejobs_ph"),
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    data = json.loads((outcome.out_dir / "metadata.json").read_text(encoding="utf-8"))
    # D1: job_title and company_name added to ParsedJD (optional, default None).
    expected_keys = {
        "must_haves",
        "nice_to_haves",
        "tone",
        "seniority",
        "red_flags",
        "raw_text_length",
        "job_title",
        "company_name",
    }
    assert set(data["parsed_jd"].keys()) == expected_keys
    # OJ.ph still flows through as the classified source_board (top-level key).
    assert data["source_board"] == "onlinejobs_ph"
