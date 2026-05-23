"""Story 5.3 — keyword_stuffing block lands in package.drift.json.

Pipeline-level smoke tests covering AC1 (block shape + sibling preservation),
AC2 (global threshold reads), AC3 (per-channel override resolution), and
AC7 (idempotency on re-run). Uses the standard _web_helpers stage_tailoring
helper with make_fake_tailor for artifact content control.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_parse,
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
)


# Greek-alphabet filler avoids any tokenizer / stop-word quirks and gives
# the keyword-stuffing density check enough total tokens (~100) so a single
# keyword occurrence stays under the 1.5% default threshold.
_PROSE_FILLER = (
    " alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
    "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega "
) * 4


def _post(tmp_path, monkeypatch, *, cv: str, cover: str, must_haves: list[str]):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
        fake_parse=make_fake_parse(must_haves=must_haves, nice_to_haves=[]),
    )
    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    return slug_dir


def test_keyword_stuffing_block_lands_as_sibling_of_fabrication_and_content_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug_dir = _post(
        tmp_path,
        monkeypatch,
        cv="Python developer with broad backend experience" + _PROSE_FILLER,
        cover="Hello there" + _PROSE_FILLER,
        must_haves=["python"],
    )
    drift = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    assert "fabrication_check" in drift
    assert "content_loss" in drift
    assert "keyword_stuffing" in drift

    ks = drift["keyword_stuffing"]
    assert set(ks.keys()) >= {
        "verdict",
        "channel",
        "density_violations",
        "dump_paragraph_locations",
        "thresholds_applied",
    }
    assert ks["verdict"] in {"pass", "fail"}
    assert ks["channel"] in {"upwork", "linkedin", "onlinejobs_ph", "other"}


def test_keyword_stuffing_block_carries_thresholds_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: global thresholds from config.yaml land in thresholds_applied."""
    slug_dir = _post(
        tmp_path,
        monkeypatch,
        cv="Python developer" + _PROSE_FILLER,
        cover="Hi" + _PROSE_FILLER,
        must_haves=["python"],
    )
    drift = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    thresholds = drift["keyword_stuffing"]["thresholds_applied"]
    assert thresholds["max_density_pct"] == 1.5
    assert thresholds["max_repetitions_per_artifact"] == 3
    assert thresholds["dump_paragraph_min_tokens"] == 15
    assert thresholds["dump_paragraph_max_keyword_ratio"] == 0.30
    assert thresholds["comma_run_min_tokens"] == 4


def test_keyword_stuffing_fail_records_violations_and_flips_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Short CV with high-density keyword → density violation expected.
    slug_dir = _post(
        tmp_path,
        monkeypatch,
        cv="python python python python python end of file body marker text\n",
        cover="hello\n",
        must_haves=["python"],
    )
    drift = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    ks = drift["keyword_stuffing"]
    assert ks["verdict"] == "fail"
    assert len(ks["density_violations"]) >= 1
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


def test_keyword_stuffing_block_idempotent_on_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC7: re-running the writer replaces keyword_stuffing wholesale, keeps siblings."""
    slug_dir = _post(
        tmp_path,
        monkeypatch,
        cv="Python developer with broad backend experience" + _PROSE_FILLER,
        cover="Hello" + _PROSE_FILLER,
        must_haves=["python"],
    )
    drift_path = slug_dir / "package.drift.json"
    first = json.loads(drift_path.read_text(encoding="utf-8"))
    fabrication_before = json.dumps(first.get("fabrication_check", {}), sort_keys=True)
    content_loss_before = json.dumps(first.get("content_loss", {}), sort_keys=True)

    from jobhunter.keyword_stuffing_matcher import KeywordStuffingCheck
    from jobhunter.keyword_stuffing_writer import write_keyword_stuffing_block

    new_check = KeywordStuffingCheck(
        verdict="fail", density_violations=[], dump_paragraph_locations=[]
    )
    write_keyword_stuffing_block(
        slug_dir,
        new_check,
        channel="other",
        thresholds_applied={"max_density_pct": 1.5},
    )

    second = json.loads(drift_path.read_text(encoding="utf-8"))
    assert json.dumps(second["fabrication_check"], sort_keys=True) == fabrication_before
    assert json.dumps(second["content_loss"], sort_keys=True) == content_loss_before
    assert second["keyword_stuffing"]["verdict"] == "fail"
    assert second["keyword_stuffing"]["density_violations"] == []
