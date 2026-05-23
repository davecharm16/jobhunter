"""Story 4.2 AC6: held-package writer fires on content-loss-only fails.

Drives the whole pipeline through POST /api/paste with three fixture shapes:

1. Fabrication passes, content-loss fails -> `package.held.json` is written,
   `metadata.held` is True, `dropped_high_impact_entries[]` is populated.
2. Fabrication fails, content-loss passes -> existing Story 3.4 behavior;
   verified here that the additive `dropped_high_impact_entries[]` is empty.
3. Both fail -> single held.json carries BOTH `failed_claims[]` AND
   `dropped_high_impact_entries[]`.

The deferred piece from Story 4.1 is exercised here: previously a content-loss
fail flipped the verdict in metadata but did NOT write a held.json or set
`metadata.held = True`. Story 4.2 closes that gap.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_parse,
    make_fake_tailor,
    stage_tailoring,
)


# ---- canonical-CV staging with Story 2.1 extensions -----------------------


def _cv_with_high_impact() -> dict[str, Any]:
    """Canonical CV with one high-impact work entry tagged for relevance tests."""
    return {
        "basics": {
            "name": "Test Author",
            "label": "Engineer",
            "email": "test@example.com",
        },
        "work": [
            {
                "name": "Acme",
                "position": "Senior Engineer",
                "startDate": "2020-01-01",
                "tags": ["typescript", "node"],
                "highImpact": True,
                "highlights": [
                    "Shipped a TypeScript ingestion service that cut latency by 60%",
                ],
            }
        ],
        "skills": [
            {"name": "Backend", "keywords": ["Python", "pytest"]},
        ],
    }


def _stage_canonical_cv_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cv: dict[str, Any]
) -> Path:
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(json.dumps(cv), encoding="utf-8")
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def _make_extractor(
    claims_by_artifact: dict[str, list[dict[str, Any]]],
) -> Callable[..., ClaimExtractionResult]:
    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        raw = claims_by_artifact.get(source_artifact, [])
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


def _zero_cost_extractor(
    markdown_text: str,
    source_artifact: str,
    *,
    api_key: str,
    timeout_seconds: float,
    prompt: Any,
) -> ClaimExtractionResult:
    return ClaimExtractionResult(
        claims=[],
        cost_usd=Decimal("0"),
        input_tokens=0,
        output_tokens=0,
    )


def _stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cv: str,
    cover: str,
    extractor: Callable[..., ClaimExtractionResult] | None = None,
    parser=None,
):
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
        fake_parse=parser,
    )
    if extractor is not None:
        inner_run = api_module.run_tailoring

        def wrapped(canonical_cv, jd_text, **kwargs):
            kwargs.setdefault("llm_extract_claims", extractor)
            return inner_run(canonical_cv, jd_text, **kwargs)

        monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root, ledger_path


# ---- AC6 scenario 1: content-loss-only fail -> held.json + held=True ------


def test_paste_writes_held_json_on_content_loss_only_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: fabrication passes, content-loss fails -> held.json is written."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- completely unrelated content\n",
        cover="generic boilerplate\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    assert response.status_code == 200

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    held_path = slug_dir / "package.held.json"
    assert held_path.exists(), (
        f"package.held.json missing on content-loss-only fail; "
        f"out_dir contents: {list(slug_dir.iterdir())}"
    )


def test_content_loss_only_fail_records_held_true_in_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: metadata.held flips True even though fabrication passed."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- completely unrelated content\n",
        cover="generic boilerplate\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is True
    assert metadata["held_path"] == str(slug_dir / "package.held.json")
    assert metadata["drift_verdicts"]["fabrication"] == "pass"
    assert metadata["drift_verdicts"]["content_loss"] == "fail"


def test_content_loss_only_fail_populates_dropped_high_impact_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: `dropped_high_impact_entries[]` carries the silently_lost drop."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- nothing relevant\n",
        cover="generic boilerplate\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=["node"]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    held = json.loads((slug_dir / "package.held.json").read_text(encoding="utf-8"))
    # Fabrication side stays empty.
    assert held["failed_claims"] == []
    # Content-loss side carries the silently_lost drop.
    drops = held["dropped_high_impact_entries"]
    assert len(drops) == 1
    drop = drops[0]
    assert set(drop.keys()) == {
        "entry_id",
        "section",
        "primary_text",
        "jd_requirements_addressed",
        "reason",
    }
    assert drop["reason"] == "silently_lost"
    assert drop["section"] == "work"
    # AC3 surface — the JD requirements are persisted verbatim.
    assert set(drop["jd_requirements_addressed"]) == {"typescript", "node"}


# ---- AC6 scenario 2: fabrication fails, content-loss passes ---------------


def test_fabrication_only_fail_keeps_dropped_high_impact_entries_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6 negative: fabrication-only fail leaves content-loss list empty (sanity)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    extractor = _make_extractor(
        {
            "cv": [
                {
                    "claim_type": "metric",
                    "claim_text": "fabricated 99x throughput",
                    "line_number": 1,
                }
            ],
            "cover_letter": [],
        }
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        # Chunk-match the full TypeScript highlight so content-loss passes.
        cv=(
            "fabricated 99x throughput\n"
            "Shipped a TypeScript ingestion service that cut latency by 60%\n"
        ),
        cover="hi\n",
        extractor=extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    held = json.loads((slug_dir / "package.held.json").read_text(encoding="utf-8"))
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["fabrication"] == "fail"
    assert metadata["drift_verdicts"]["content_loss"] == "pass"
    assert metadata["held"] is True
    # Fabrication populates `failed_claims`; content-loss list stays empty.
    assert len(held["failed_claims"]) >= 1
    assert held["dropped_high_impact_entries"] == []


# ---- AC6 scenario 3: BOTH fail -> combined held sidecar -------------------


def test_both_checks_fail_yields_combined_held_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: when fabrication AND content-loss both fail, ONE held.json is
    written carrying BOTH `failed_claims[]` and `dropped_high_impact_entries[]`."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    extractor = _make_extractor(
        {
            "cv": [
                {
                    "claim_type": "metric",
                    "claim_text": "fabricated 99x throughput",
                    "line_number": 1,
                }
            ],
            "cover_letter": [],
        }
    )
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        # `fabricated 99x throughput` is the unsourced claim. The TypeScript
        # highlight is intentionally absent -> content-loss also fails.
        cv="# CV\nfabricated 99x throughput\n",
        cover="hi\n",
        extractor=extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    held = json.loads((slug_dir / "package.held.json").read_text(encoding="utf-8"))
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["fabrication"] == "fail"
    assert metadata["drift_verdicts"]["content_loss"] == "fail"
    assert metadata["held"] is True
    assert len(held["failed_claims"]) >= 1
    assert len(held["dropped_high_impact_entries"]) >= 1


# ---- pass case: neither check fails -> no held sidecar --------------------


def test_both_checks_pass_writes_no_held_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: when both checks pass, no held.json appears (Story 3.4 contract preserved)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    # Story 5.3: CV extended with ~80-token prose filler so the new
    # keyword-stuffing density check doesn't trip on a short body where
    # "typescript" would land above the 1.5% density threshold. The
    # high-impact chunk-match still works (matcher does `chunk in haystack`).
    # ~100 distinct tokens — Greek-alphabet padding sidesteps any
    # stop-word / short-token tokenizer quirks.
    filler = (
        " alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
        "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega "
    ) * 4
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv=(
            "# CV\n\n"
            "- Shipped a TypeScript ingestion service that cut latency by 60%\n\n"
            + filler + "\n"
        ),
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is False
    assert metadata["held_path"] is None
    assert not (slug_dir / "package.held.json").exists()


# ---- AC6: irrelevant_to_jd drops do NOT show up on held.json --------------


def test_irrelevant_to_jd_drops_do_not_appear_on_held_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`irrelevant_to_jd` is the logged-rationale, non-failing reason code; if
    it ends up on `dropped_high_impact_entries[]` then `GET /api/queue` would
    mis-report the fail-cause. Verifies the held writer filters it out."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())

    # Compute the entry_id the matcher will assign so we can target it via the
    # trace.
    from jobhunter.content_loss_matcher import iter_high_impact_relevant

    relevant = iter_high_impact_relevant(
        _cv_with_high_impact(),
        {"must_haves": ["typescript"], "nice_to_haves": []},
    )
    target_entry_id = relevant[0].entry_id

    # Seed a logged-rationale trace so the only drop is `irrelevant_to_jd`.
    # AC2: that reason code does NOT contribute to fail, so the package is
    # NOT held — there is no held.json on disk. Drive that path through the
    # pipeline by patching the trace writer.
    import jobhunter.tailoring as tailoring_module

    original_write_trace = tailoring_module._write_tailoring_trace

    def patched_write_trace(out_dir: Path):
        path = original_write_trace(out_dir)
        path.write_text(
            json.dumps(
                {
                    "dropped_entries": [
                        {
                            "entry_id": target_entry_id,
                            "reason": "irrelevant_to_jd",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr(
        tailoring_module, "_write_tailoring_trace", patched_write_trace
    )

    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- nothing relevant\n",
        cover="boilerplate\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    # AC2 contract: irrelevant_to_jd alone does not fail the check.
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["drift_verdicts"]["content_loss"] == "pass"
    assert metadata["held"] is False
    # And the held.json must not exist (the package is not held).
    assert not (slug_dir / "package.held.json").exists()
