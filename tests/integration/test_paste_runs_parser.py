"""Integration test: POST /api/paste runs the structured JD parser (Story 2.3).

Covers AC1 (parsed JD persisted to metadata sidecar) and AC2 (downstream
stages read from the parsed object — verified by the outcome carrying it
and the metadata sidecar exposing it).
"""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_parse,
    stage_canonical_cv,
    stage_tailoring,
)

from jobhunter.jd_parser import ParsedJD
from jobhunter.llm_client import TailoringResult
from jobhunter.runtime_config import RuntimeConfig
from jobhunter.tailoring import TailoringOutcome, run_tailoring
from jobhunter.web.api import create_app

# --- AC1: parsed_jd is persisted to the metadata sidecar -----------------


def test_paste_writes_parsed_jd_to_metadata_sidecar(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_parse=make_fake_parse(
            must_haves=["Python", "FastAPI"],
            nice_to_haves=["Docker"],
            tone="casual",
            seniority="senior",
            red_flags=["vague scope"],
        ),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    metadata_path = slug_dirs[0] / "metadata.json"
    assert metadata_path.exists()

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["parsed_jd"] != {}
    assert data["parsed_jd"]["must_haves"] == ["Python", "FastAPI"]
    assert data["parsed_jd"]["nice_to_haves"] == ["Docker"]
    assert data["parsed_jd"]["tone"] == "casual"
    assert data["parsed_jd"]["seniority"] == "senior"
    assert data["parsed_jd"]["red_flags"] == ["vague scope"]
    assert data["parsed_jd"]["raw_text_length"] == len("Senior Python role.\n")
    # AC3: success path leaves no `error` field set.
    assert data["error"] is None


# --- AC2: parsed_jd surfaces on TailoringOutcome -------------------------


def test_run_tailoring_outcome_carries_parsed_jd_dict(tmp_path) -> None:
    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )

    def fake_parse(jd_text, *, api_key, timeout_seconds, prompt):
        return ParsedJD(
            must_haves=["Python"],
            nice_to_haves=["Docker"],
            tone="formal",
            seniority="staff",
            red_flags=[],
            raw_text_length=len(jd_text),
        )

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
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
        config=config,
        llm_tailor=fake_tailor,
        llm_parse=fake_parse,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )
    assert isinstance(outcome, TailoringOutcome)
    assert outcome.parsed_jd != {}
    assert outcome.parsed_jd["must_haves"] == ["Python"]
    assert outcome.parsed_jd["seniority"] == "staff"
    assert outcome.parsed_jd["raw_text_length"] == len("Senior Python role.\n")


# --- AC1 ordering: parse runs BEFORE the tailor LLM call -----------------


def test_parse_runs_before_tailor(tmp_path, monkeypatch) -> None:
    """If the parse step short-circuits (failure), the tailor step must not
    be invoked. This pins the orchestrator's ordering: parse first.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    tailor_calls = {"count": 0}

    def must_not_run(*args, **kwargs):
        tailor_calls["count"] += 1
        raise AssertionError("tailor must not run when parse fails")

    from jobhunter.jd_parser import ParseTimedOut

    def timing_out_parse(*args, **kwargs):
        raise ParseTimedOut("simulated parse timeout")

    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=must_not_run,
        fake_parse=timing_out_parse,
    )

    client = TestClient(create_app(), raise_server_exceptions=False)
    client.post("/api/paste", json={"jd_text": "JD.\n", "source": "browser"})
    assert tailor_calls["count"] == 0


# --- AC1: parsed_jd dict has the documented keys -------------------------


def test_parsed_jd_dict_has_expected_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    data = json.loads((slug_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
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
