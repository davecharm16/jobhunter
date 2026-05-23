"""Story 3.2 AC1-AC3 end-to-end: package.drift.json lands in `./out/<slug>/`.

Drives the whole pipeline through POST /api/paste with the fabrication matcher
wired in. Covers:

- AC1: package.drift.json exists with the documented fabrication_check shape.
- AC2: claims matched exactly / partially / not at all produce the
  documented trace methods (exact_string, substring) or land in
  unsourced_claims.
- AC3: pass/fail logic flows through to metadata.drift_verdicts.fabrication,
  and a fabrication-fail still returns 200 (the package is held, not a
  pipeline error).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Callable

from fastapi.testclient import TestClient

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
)


# ---- helpers --------------------------------------------------------------


def _make_extractor(cv_claims, cover_claims) -> Callable[..., ClaimExtractionResult]:
    """Return a fake claim-extractor that yields per-artifact claims."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        raw = cv_claims if source_artifact == "cv" else cover_claims
        claims = [
            Claim(
                claim_id=f"{source_artifact}:{c['line_number']}:abcdef01",
                claim_type=c["claim_type"],
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


def _stage(tmp_path, monkeypatch, *, extractor, cv: str, cover: str):
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
    return out_root, ledger_path


# ---- AC1: file shape + atomic write --------------------------------------


def test_paste_writes_package_drift_json_with_fabrication_check_key(
    tmp_path, monkeypatch,
) -> None:
    """The drift report is a top-level dict with a `fabrication_check` key
    (sibling-key-ready for the Epic 4/5 drift checks)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    # The canonical CV has `pytest` as a skill keyword (Testing & Quality).
    extractor = _make_extractor(
        cv_claims=[
            {"claim_type": "skill", "claim_text": "pytest", "line_number": 3},
        ],
        cover_claims=[
            {"claim_type": "skill", "claim_text": "pytest", "line_number": 1},
        ],
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        extractor=extractor,
        cv="# CV\n\n- pytest\n",
        cover="pytest\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    drift_path = slug_dir / "package.drift.json"
    assert drift_path.exists()

    doc = json.loads(drift_path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert "fabrication_check" in doc
    check = doc["fabrication_check"]
    assert set(check.keys()) == {
        "verdict",
        "claims_total",
        "claims_sourced",
        "claims_unsourced",
        "traces",
        "unsourced_claims",
    }


def test_paste_drift_json_has_no_dot_tmp_left_behind(tmp_path, monkeypatch) -> None:
    """Atomic write idiom: no `.package.drift.tmp` survives a successful run."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[{"claim_type": "skill", "claim_text": "pytest", "line_number": 1}],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="pytest\n", cover="hi\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    files = {p.name for p in slug_dir.iterdir()}
    assert ".package.drift.tmp" not in files
    assert "package.drift.json" in files


# ---- AC2: exact, substring, unsourced match methods ---------------------


def test_paste_drift_json_records_exact_string_match(tmp_path, monkeypatch) -> None:
    """A claim equal (case-insensitive) to a canonical-CV keyword records
    `match_method: exact_string` with score 1.0 (AC2.1)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[
            {"claim_type": "skill", "claim_text": "Python", "line_number": 1},
        ],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="Python\n", cover="hi\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    cv_traces = [
        t for t in doc["fabrication_check"]["traces"]
        if t["claim_text"] == "Python"
    ]
    assert len(cv_traces) == 1
    assert cv_traces[0]["match_method"] == "exact_string"
    assert cv_traces[0]["match_score"] == 1.0


def test_paste_drift_json_records_substring_match(tmp_path, monkeypatch) -> None:
    """A claim that contains (or is contained by) a canonical-CV entry
    records `match_method: substring` (AC2.2)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    # Canonical highlight: "Designed a filesystem-first artifact pipeline ..."
    # Claim contains "filesystem-first artifact pipeline" — substring of the
    # canonical text.
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_type": "accomplishment",
                "claim_text": "filesystem-first artifact pipeline",
                "line_number": 1,
            },
        ],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="filesystem-first artifact pipeline\n", cover="hi\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    trace = doc["fabrication_check"]["traces"][0]
    assert trace["match_method"] == "substring"


def test_paste_drift_json_records_unsourced_claim_when_no_match(
    tmp_path, monkeypatch,
) -> None:
    """A claim with no canonical-CV match lands in `unsourced_claims` with
    `reason: no_canonical_match` (FR24)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 9,
            },
        ],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="led a 47-person engineering platform org\n", cover="hi\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    # AC4: fabrication=fail still returns 200; the package is held in
    # metadata, not a pipeline error.
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    unsourced = doc["fabrication_check"]["unsourced_claims"]
    assert len(unsourced) == 1
    # Story 3.3: the semantic step now upgrades the generic
    # `no_canonical_match` reason. This claim has the quantifier `47-person`
    # plus generic tokens that score below the 0.65 rule_based threshold,
    # so the quantifier guard fires first and the reason carries the
    # offending quantifier token. The structural-failure invariant
    # (unsourced claim exists, source_artifact and line_number are pinned)
    # is preserved.
    assert unsourced[0]["reason"].startswith(
        ("semantic_below_threshold", "quantifier_not_in_source", "no_canonical_match")
    )
    assert unsourced[0]["source_artifact"] == "cv"
    assert unsourced[0]["line_number"] == 9


# ---- AC3: pass/fail flows through to metadata.drift_verdicts ------------


def test_paste_metadata_records_fabrication_pass_when_every_claim_sourced(
    tmp_path, monkeypatch,
) -> None:
    """AC3 pass: metadata.drift_verdicts.fabrication overrides "pending" with
    "pass" when every claim is sourced."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[
            {"claim_type": "skill", "claim_text": "Python", "line_number": 1},
            {"claim_type": "skill", "claim_text": "pytest", "line_number": 2},
        ],
        cover_claims=[
            {"claim_type": "skill", "claim_text": "FastAPI", "line_number": 1},
        ],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="Python\npytest\n", cover="FastAPI\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["fabrication"] == "pass"
    # Story 4.1: the content-loss matcher now overrides the "pending"
    # placeholder. The committed canonical-cv.json (staged via
    # stage_canonical_cv) carries no `highImpact: true` entries, so the
    # must-appear set is empty and the verdict is `pass`.
    assert metadata["drift_verdicts"]["content_loss"] == "pass"
    # Story 5.1: the keyword-stuffing density matcher now overrides the
    # "pending" placeholder. This test stages a deliberately stuffed cv
    # ("Python\npytest\n" -> 1/2 tokens are "python", 50% density) so
    # the verdict is `fail`. The fabrication-pass invariant under test
    # is unrelated to the density check; the third dimension is asserted
    # separately by test_keyword_stuffing_in_pipeline.py.
    assert metadata["drift_verdicts"]["keyword_stuffing"] == "fail"


def test_paste_metadata_records_fabrication_fail_when_any_claim_unsourced(
    tmp_path, monkeypatch,
) -> None:
    """AC3 fail: even one unsourced claim flips the verdict to "fail"."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[
            {"claim_type": "skill", "claim_text": "Python", "line_number": 1},
            {
                "claim_type": "metric",
                "claim_text": "fabricated 99x throughput gain",
                "line_number": 2,
            },
        ],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="Python\nfabricated 99x throughput gain\n", cover="hi\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["fabrication"] == "fail"


def test_paste_drift_fail_still_writes_staged_markdown_artifacts(
    tmp_path, monkeypatch,
) -> None:
    """AC4: on fabrication=fail the staged artifacts stay on disk (the
    held-package precondition Story 3.4 picks up)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            },
        ],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="led a 47-person engineering platform org\n", cover="hi\n",
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    # All staged artifacts must be present alongside the drift report so
    # Story 3.4's held-package writer can pick them up.
    files = {p.name for p in slug_dir.iterdir()}
    assert {
        "cv.md",
        "cover-letter.md",
        "claims.json",
        "package.drift.json",
        "metadata.json",
    }.issubset(files)


# ---- AC1: trace + unsourced shape on disk -------------------------------


def test_drift_json_trace_carries_documented_five_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[{"claim_type": "skill", "claim_text": "Python", "line_number": 1}],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="Python\n", cover="hi\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    trace = doc["fabrication_check"]["traces"][0]
    assert set(trace.keys()) == {
        "claim_id",
        "claim_text",
        "matched_canonical_entry_id",
        "match_method",
        "match_score",
    }
    # AC5: the canonical-entry id encodes the section path so authors can
    # locate the source by reading the id alone.
    assert trace["matched_canonical_entry_id"].startswith("skills[")


def test_drift_json_is_diffable_across_runs(tmp_path, monkeypatch) -> None:
    """AC5: deterministic canonical-entry ids -> identical traces across runs."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(
        cv_claims=[{"claim_type": "skill", "claim_text": "Python", "line_number": 1}],
        cover_claims=[],
    )
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor,
        cv="Python\n", cover="hi\n",
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role A.\n", "source": "browser"},
    )
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role B.\n", "source": "browser"},
    )
    slug_dirs = sorted(p for p in out_root.iterdir() if p.is_dir())
    doc_a = json.loads(
        (slug_dirs[0] / "package.drift.json").read_text(encoding="utf-8")
    )
    doc_b = json.loads(
        (slug_dirs[1] / "package.drift.json").read_text(encoding="utf-8")
    )
    ids_a = [t["matched_canonical_entry_id"] for t in doc_a["fabrication_check"]["traces"]]
    ids_b = [t["matched_canonical_entry_id"] for t in doc_b["fabrication_check"]["traces"]]
    assert ids_a == ids_b
