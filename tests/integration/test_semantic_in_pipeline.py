"""Integration tests for the Story 3.3 semantic step in the pipeline.

Drives the whole pipeline through `POST /api/paste` with a custom canonical
CV staged on disk so the spec's fixture pair lands in
`./out/<slug>/package.drift.json`:

- AC2 above-threshold honest paraphrase records `match_method: "semantic"`.
- AC2 below-threshold rejection records the literal reason format.
- AC3 quantifier guard rejects with `quantifier_not_in_source (quantifier=<tok>)`
  for the load-bearing fixture pair "led the engineering team" /
  "led a 3-person engineering team".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from tests.integration._web_helpers import make_fake_tailor, stage_tailoring

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.web.api import create_app


def _stage_canonical_cv(tmp_path: Path, monkeypatch, cv_doc: dict) -> Path:
    """Write *cv_doc* to disk and point the canonical-CV reader at it."""
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(json.dumps(cv_doc), encoding="utf-8")
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def _make_extractor(cv_claims) -> Callable[..., ClaimExtractionResult]:
    """Return a fake claim-extractor that emits *cv_claims* for the cv artifact."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        raw = cv_claims if source_artifact == "cv" else []
        claims = [
            Claim(
                claim_id=f"{source_artifact}:{c['line_number']}:abcdef01",
                claim_type=c.get("claim_type", "accomplishment"),
                claim_text=c["claim_text"],
                source_artifact=source_artifact,
                line_number=c["line_number"],
            )
            for c in raw
        ]
        return ClaimExtractionResult(
            claims=claims,
            cost_usd=Decimal("0.000420"),
            input_tokens=42,
            output_tokens=21,
        )

    return fake_extract


def _stage(tmp_path, monkeypatch, *, extractor, cv: str, cover: str = "hi\n"):
    """Wire stage_tailoring + the extractor through the FastAPI route."""
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
    )

    inner_run = api_module.run_tailoring

    def wrapped(canonical_cv, jd_text, **kwargs):
        kwargs.setdefault("llm_extract_claims", extractor)
        return inner_run(canonical_cv, jd_text, **kwargs)

    monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root


def _read_drift(out_root: Path) -> dict:
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    return json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))


# ---- AC2: above-threshold honest paraphrase records semantic match -------


def test_semantic_match_above_threshold_records_trace_with_semantic_method(
    tmp_path, monkeypatch,
) -> None:
    """A claim that paraphrases the canonical text (above 0.65 rule_based
    threshold) records `match_method: "semantic"` with the actual score."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv(
        tmp_path,
        monkeypatch,
        {"basics": {"name": "X"}, "work": [{"highlights": ["led the team"]}]},
    )
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_text": "led the engineering team",
                "line_number": 1,
                "claim_type": "responsibility",
            },
        ],
    )
    out_root = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="led the engineering team\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    doc = _read_drift(out_root)
    fab = doc["fabrication_check"]
    assert fab["verdict"] == "pass"
    assert len(fab["traces"]) == 1
    trace = fab["traces"][0]
    assert trace["match_method"] == "semantic"
    assert trace["match_score"] >= 0.65
    assert trace["claim_text"] == "led the engineering team"


# ---- AC2: below-threshold rejection literal-format reason ---------------


def test_semantic_below_threshold_records_specific_reason(
    tmp_path, monkeypatch,
) -> None:
    """When every canonical entry scores below threshold, the unsourced
    claim's reason follows the literal `semantic_below_threshold
    (score=<x>, threshold=<y>)` format."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv(
        tmp_path,
        monkeypatch,
        {
            "basics": {"name": "X"},
            "work": [{"highlights": ["wrote internal documentation"]}],
        },
    )
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_text": "scaled the kubernetes platform",
                "line_number": 1,
                "claim_type": "accomplishment",
            },
        ],
    )
    out_root = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="scaled the kubernetes platform\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    doc = _read_drift(out_root)
    fab = doc["fabrication_check"]
    assert fab["verdict"] == "fail"
    assert len(fab["unsourced_claims"]) == 1
    reason = fab["unsourced_claims"][0]["reason"]
    assert reason.startswith("semantic_below_threshold (score=")
    assert "threshold=0.6500" in reason
    assert reason.endswith(")")


# ---- AC3: quantifier guard - the spec's load-bearing fixture pair -------


def test_quantifier_mismatch_fails_with_documented_reason(
    tmp_path, monkeypatch,
) -> None:
    """The spec's fixture pair: canonical "led the engineering team",
    tailored "led a 3-person engineering team" - semantic similarity is
    above threshold but the quantifier guard catches `3-person`, so the
    package fails with `quantifier_not_in_source (quantifier=3-person)`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv(
        tmp_path,
        monkeypatch,
        {
            "basics": {"name": "X"},
            "work": [{"highlights": ["led the engineering team"]}],
        },
    )
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_text": "led a 3-person engineering team",
                "line_number": 1,
                "claim_type": "responsibility",
            },
        ],
    )
    out_root = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="led a 3-person engineering team\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    # AC3: package fails (verdict: fail) but pipeline still returns 200 - the
    # held-package writer (Story 3.4) consumes the drift report from disk.
    assert response.status_code == 200

    doc = _read_drift(out_root)
    fab = doc["fabrication_check"]
    assert fab["verdict"] == "fail"
    assert len(fab["unsourced_claims"]) == 1
    unsourced = fab["unsourced_claims"][0]
    assert unsourced["reason"] == "quantifier_not_in_source (quantifier=3-person)"
    assert unsourced["claim_text"] == "led a 3-person engineering team"
    assert unsourced["source_artifact"] == "cv"
    assert unsourced["line_number"] == 1


def test_quantifier_in_source_passes_semantic_match(
    tmp_path, monkeypatch,
) -> None:
    """When the canonical CV already carries the quantifier verbatim, the
    guard stays silent and the semantic match goes through cleanly."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv(
        tmp_path,
        monkeypatch,
        {
            "basics": {"name": "X"},
            "work": [{"highlights": ["led a 3-person engineering team"]}],
        },
    )
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_text": "led a 3-person team",
                "line_number": 1,
                "claim_type": "responsibility",
            },
        ],
    )
    out_root = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="led a 3-person team\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    doc = _read_drift(out_root)
    fab = doc["fabrication_check"]
    assert fab["verdict"] == "pass"
    assert len(fab["traces"]) == 1
    assert fab["traces"][0]["match_method"] == "semantic"


# ---- Verdict still flows through to metadata.drift_verdicts -------------


def test_quantifier_guard_failure_records_fabrication_fail_in_metadata(
    tmp_path, monkeypatch,
) -> None:
    """Same fixture pair end-to-end: metadata.drift_verdicts.fabrication ==
    "fail" when the quantifier guard rejects."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv(
        tmp_path,
        monkeypatch,
        {
            "basics": {"name": "X"},
            "work": [{"highlights": ["led the engineering team"]}],
        },
    )
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_text": "led a 3-person engineering team",
                "line_number": 1,
                "claim_type": "responsibility",
            },
        ],
    )
    out_root = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="led a 3-person engineering team\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["fabrication"] == "fail"
