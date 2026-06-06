"""Integration: Upwork signal extractor wired into POST /api/paste (Story 2.5).

Covers AC1 (signals populated on the parsed object and surfaced for the
proposal stage), AC2 (budget-below-floor red flag lands in metadata's
`parsed_jd.red_flags`), AC3 (vague-scope red flag lands in metadata), and
AC4 (screening questions plumb through to the in-memory parsed object).
"""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi.testclient import TestClient

from jobhunter.jd_parser import ParsedJD
from jobhunter.llm_client import TailoringResult
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.tailoring import run_tailoring
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_classifier,
    make_fake_parse,
    stage_canonical_cv,
    stage_tailoring,
)


# --- AC1: signals reach the in-memory parsed object via run_tailoring ----


def test_run_tailoring_populates_upwork_signals_on_parsed(tmp_path) -> None:
    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    captured: dict = {}

    def fake_parse(jd_text, *, api_key, timeout_seconds, prompt):
        parsed = ParsedJD(
            must_haves=["Python"],
            nice_to_haves=["FastAPI"],
            tone="neutral",
            seniority="senior",
            red_flags=[],
            raw_text_length=len(jd_text),
        )
        captured["parsed"] = parsed
        return parsed

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    jd_text = (
        "Senior Python role on upwork.com.\n"
        "Budget: $40/hr.\n\n"
        "Screening Questions:\n"
        "- Why are you a fit?\n"
        "- Earliest start?\n"
    )
    run_tailoring(
        {"basics": {"name": "X"}},
        jd_text,
        config=config,
        llm_tailor=fake_tailor,
        llm_parse=fake_parse,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    parsed: ParsedJD = captured["parsed"]
    assert "upwork" in parsed.signals
    upwork = parsed.signals["upwork"]
    assert upwork["pricing_type"] == "hourly"
    assert upwork["budget_band"] == "$40/hr"
    assert upwork["screening_questions"] == [
        "Why are you a fit?",
        "Earliest start?",
    ]


def test_extractor_skipped_for_non_upwork_boards(tmp_path) -> None:
    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    captured: dict = {}

    def fake_parse(jd_text, *, api_key, timeout_seconds, prompt):
        parsed = ParsedJD(
            must_haves=["Python"],
            nice_to_haves=[],
            tone="neutral",
            seniority="senior",
            red_flags=[],
            raw_text_length=len(jd_text),
        )
        captured["parsed"] = parsed
        return parsed

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    # JD with budget pattern but LinkedIn classification — extractor must NOT run.
    jd_text = "LinkedIn Easy Apply. Budget $5/hr. please make it amazing.\n"
    run_tailoring(
        {"basics": {"name": "X"}},
        jd_text,
        config=config,
        llm_tailor=fake_tailor,
        llm_parse=fake_parse,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    parsed: ParsedJD = captured["parsed"]
    assert parsed.signals == {}
    # red_flags must NOT include the Upwork-only flags.
    assert "budget_below_floor" not in parsed.red_flags
    assert "vague_scope" not in parsed.red_flags


# --- AC2: budget-below-floor red flag lands in metadata ------------------


def test_budget_below_floor_red_flag_in_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": (
                "Posted on upwork.com.\n"
                "Budget: $10/hr (long-term).\n"
            ),
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "upwork"
    assert "budget_below_floor" in metadata["parsed_jd"]["red_flags"]


def test_fixed_budget_below_floor_red_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": (
                "Posted on upwork.com.\n"
                "Project budget: $250 (one-off).\n"
            ),
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "upwork"
    assert "budget_below_floor" in metadata["parsed_jd"]["red_flags"]


def test_budget_above_floor_no_red_flag(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Posted on upwork.com.\nBudget: $75/hr.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert "budget_below_floor" not in metadata["parsed_jd"]["red_flags"]


# --- AC3: vague-scope red flag lands in metadata -------------------------


def test_vague_scope_red_flag_in_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": (
                "Posted on upwork.com.\n"
                "Budget: $50/hr.\n"
                "Looking for someone awesome to lead this.\n"
            ),
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert "vague_scope" in metadata["parsed_jd"]["red_flags"]
    # The budget is above floor, so only vague_scope fires.
    assert "budget_below_floor" not in metadata["parsed_jd"]["red_flags"]


def test_both_red_flags_can_fire_together(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": (
                "Posted on upwork.com.\n"
                "Budget: $10/hr.\n"
                "Need a rockstar dev.\n"
            ),
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    flags = metadata["parsed_jd"]["red_flags"]
    assert "budget_below_floor" in flags
    assert "vague_scope" in flags


# --- AC4: screening questions reach the in-memory parsed object ----------


def test_screening_questions_plumbed_through_parsed_signals(
    tmp_path, monkeypatch,
) -> None:
    """Screening questions land on `parsed.signals["upwork"]` for Story 2.7."""
    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )
    captured: dict = {}

    def fake_parse(jd_text, *, api_key, timeout_seconds, prompt):
        parsed = ParsedJD(
            must_haves=["Python"],
            nice_to_haves=[],
            tone="neutral",
            seniority="senior",
            red_flags=[],
            raw_text_length=len(jd_text),
        )
        captured["parsed"] = parsed
        return parsed

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="Dear team\n",
            cost_usd=Decimal("0.001"),
            input_tokens=1,
            output_tokens=1,
        )

    jd_text = (
        "Posted on upwork.com.\n"
        "Budget: $50/hr.\n\n"
        "Screening Questions:\n"
        "1. How many years of Python?\n"
        "2. Have you used FastAPI in production?\n"
        "3. Can you start within two weeks?\n"
    )
    run_tailoring(
        {"basics": {"name": "X"}},
        jd_text,
        config=config,
        llm_tailor=fake_tailor,
        llm_parse=fake_parse,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    parsed: ParsedJD = captured["parsed"]
    assert parsed.signals["upwork"]["screening_questions"] == [
        "How many years of Python?",
        "Have you used FastAPI in production?",
        "Can you start within two weeks?",
    ]


# --- Parsed_jd metadata shape preserved (signals popped) -----------------


def test_metadata_parsed_jd_keys_unchanged_when_upwork(
    tmp_path, monkeypatch,
) -> None:
    """The metadata's `parsed_jd` keeps its Story 2.3 six-key shape."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "upwork.com — $50/hr role.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    # D1: job_title and company_name added to ParsedJD (optional, default None).
    assert set(metadata["parsed_jd"].keys()) == {
        "must_haves",
        "nice_to_haves",
        "tone",
        "seniority",
        "red_flags",
        "raw_text_length",
        "job_title",
        "company_name",
    }


# --- Explicit override + extractor still runs ----------------------------


def test_explicit_upwork_override_triggers_extractor(
    tmp_path, monkeypatch,
) -> None:
    """An explicit `source_board: upwork` from the request body wires the extractor in."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path, monkeypatch, fake_classify=make_fake_classifier(source_board="other"),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Budget $10/hr. Need a rockstar.\n",
            "source": "n8n",
            "source_board": "upwork",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "upwork"
    flags = metadata["parsed_jd"]["red_flags"]
    assert "budget_below_floor" in flags
    assert "vague_scope" in flags


def _read_metadata(out_root):
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    return json.loads((slug_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
