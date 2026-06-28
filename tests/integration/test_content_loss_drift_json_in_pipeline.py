"""Story 4.2 end-to-end: package.drift.json carries the `content_loss` block.

Drives the whole pipeline through POST /api/paste with a custom canonical CV
(staged with `highImpact` + `tags` extensions) and asserts:

- AC1: `package.drift.json` carries BOTH `fabrication_check` (Story 3.2) and
  `content_loss` (Story 4.2) top-level keys. The `content_loss` block has the
  documented 5-field shape (`verdict`, `check_version`, `ran_at`,
  `preserved_entries`, `dropped_entries`).
- AC3: each dropped entry's `jd_requirements_addressed` carries the JD's
  normalized must-have / nice-to-have string verbatim.
- AC4: a re-run replaces the `content_loss` block wholesale and preserves
  `fabrication_check` byte-for-byte.
- AC5 smoke: the on-disk shape round-trips through `json.loads` without error
  and the parsed dict carries the expected keys + types.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_parse,
    make_fake_tailor,
    stage_tailoring,
)

from jobhunter.claim_extractor import ClaimExtractionResult
from jobhunter.web.api import create_app

# ---- canonical-CV staging with Story 2.1 extensions -----------------------


def _cv_with_high_impact() -> dict[str, Any]:
    """Canonical CV with two high-impact work entries tagged for relevance tests."""
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
                    "Led the on-call rotation for the payments squad",
                ],
            },
            {
                "name": "Beta Corp",
                "position": "Staff Engineer",
                "startDate": "2018-01-01",
                "tags": ["python", "fintech"],
                "highImpact": True,
                "highlights": [
                    "Built a Python billing reconciler with sub-second latency",
                ],
            },
        ],
        "skills": [
            {"name": "Backend", "keywords": ["Python", "pytest"]},
        ],
    }


def _stage_canonical_cv_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cv: dict[str, Any]
) -> Path:
    """Write *cv* into tmp_path and point `CANONICAL_CV_PATH` at it."""
    cv_path = tmp_path / "canonical-cv.json"
    cv_path.write_text(json.dumps(cv), encoding="utf-8")
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", cv_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", cv_path)
    return cv_path


def _zero_cost_extractor(
    markdown_text: str,
    source_artifact: str,
    *,
    api_key: str,
    timeout_seconds: float,
    prompt: Any,
) -> ClaimExtractionResult:
    """Emit zero claims so the fabrication matcher passes (keeps the test
    surface narrow to the content-loss block on disk)."""
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
    """Wire stage_tailoring + the extractor through the FastAPI route."""
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


# ---- AC1: drift.json carries both fabrication_check + content_loss --------


def test_paste_writes_package_drift_json_with_content_loss_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: `content_loss` lives next to `fabrication_check` on the same file."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- Shipped a TypeScript ingestion service\n",
        cover="hi\n",
        extractor=_zero_cost_extractor,
        parser=make_fake_parse(must_haves=["typescript"], nice_to_haves=[]),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior TypeScript role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    # Both top-level keys present: fabrication_check (Story 3.2) + content_loss
    # (Story 4.2).
    assert "fabrication_check" in doc
    assert "content_loss" in doc


def test_content_loss_block_has_documented_five_field_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1 on-disk shape: verdict / check_version / ran_at / preserved / dropped."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- Shipped a TypeScript ingestion service\n",
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
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    block = doc["content_loss"]
    # Story 4.3: config_snapshot added as a sixth top-level key when the
    # content-loss matcher runs. The original Story 4.2 assertion expected
    # exactly five keys; widened to absorb the snapshot.
    assert set(block.keys()) == {
        "verdict",
        "check_version",
        "ran_at",
        "preserved_entries",
        "dropped_entries",
        "config_snapshot",
    }
    assert block["check_version"] == "v1"
    # ISO 8601 UTC with `Z` suffix.
    assert block["ran_at"].endswith("Z")


def test_preserved_entry_serializes_with_four_field_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: preserved entry shape on disk."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- Shipped a TypeScript ingestion service that cut latency by 60%\n",
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
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    block = doc["content_loss"]
    assert block["verdict"] == "pass"
    assert len(block["preserved_entries"]) >= 1
    preserved = block["preserved_entries"][0]
    assert set(preserved.keys()) == {
        "entry_id",
        "section",
        "matched_in",
        "match_type",
    }
    assert preserved["section"] == "work"
    assert preserved["match_type"] == "substring"
    assert "cv.md" in preserved["matched_in"]


def test_dropped_entry_serializes_with_five_field_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: dropped entry shape on disk + AC3 fields are present."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- completely unrelated content\n",
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
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    block = doc["content_loss"]
    assert block["verdict"] == "fail"
    assert len(block["dropped_entries"]) >= 1
    dropped = block["dropped_entries"][0]
    assert set(dropped.keys()) == {
        "entry_id",
        "section",
        "primary_text",
        "jd_requirements_addressed",
        "reason",
    }


# ---- AC3: jd_requirements_addressed is populated verbatim -----------------


def test_dropped_entry_jd_requirements_addressed_carries_verbatim_jd_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: the dropped entry's `jd_requirements_addressed` carries the JD's
    must-have / nice-to-have string verbatim (lower-normalised exactly as the
    matcher produces it)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    # Two high-impact entries — only the TypeScript one overlaps a JD requirement.
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
    doc = json.loads((slug_dir / "package.drift.json").read_text(encoding="utf-8"))
    dropped = doc["content_loss"]["dropped_entries"]
    # Acme entry tags = ["typescript", "node"]; both JD requirements overlap.
    acme = next(d for d in dropped if "TypeScript" in d["primary_text"])
    assert set(acme["jd_requirements_addressed"]) == {"typescript", "node"}
    assert acme["reason"] == "silently_lost"


# ---- AC4: idempotency on re-run ------------------------------------------


def test_re_run_replaces_content_loss_block_wholesale_and_preserves_fabrication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: a re-run replaces `content_loss` wholesale. Drives the test through
    the writer directly (re-running the FastAPI route generates a different slug
    each time so the on-disk file is fresh; this test exercises the writer's
    own re-run idempotency by writing twice into the same dir)."""
    from jobhunter.content_loss_matcher import (
        ContentLossCheck,
        PreservedEntry,
    )
    from jobhunter.content_loss_writer import write_content_loss_block

    slug_dir = tmp_path / "slug"
    slug_dir.mkdir()
    # Seed the file with a synthetic fabrication_check block + stale content_loss.
    drift_path = slug_dir / "package.drift.json"
    fabrication_block = {
        "verdict": "pass",
        "claims_total": 1,
        "claims_sourced": 1,
        "claims_unsourced": 0,
        "traces": [
            {
                "claim_id": "cv:1:abcd",
                "claim_text": "Python",
                "matched_canonical_entry_id": "skills:abcdef01",
                "match_method": "exact_string",
                "match_score": 1.0,
            }
        ],
        "unsourced_claims": [],
    }
    drift_path.write_text(
        json.dumps(
            {
                "fabrication_check": fabrication_block,
                "content_loss": {
                    "verdict": "fail",
                    "check_version": "v1",
                    "ran_at": "2026-01-01T00:00:00Z",
                    "preserved_entries": [],
                    "dropped_entries": [
                        {
                            "entry_id": "stale[0]:000000",
                            "section": "work",
                            "primary_text": "stale drop",
                            "jd_requirements_addressed": ["stale"],
                            "reason": "silently_lost",
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    write_content_loss_block(
        slug_dir,
        ContentLossCheck(
            verdict="pass",
            preserved_entries=[
                PreservedEntry(
                    entry_id="work[0]:fresh1",
                    section="work",
                    matched_in=["cv.md"],
                    match_type="substring",
                )
            ],
        ),
    )

    doc = json.loads(drift_path.read_text(encoding="utf-8"))
    # Fabrication sibling untouched.
    assert doc["fabrication_check"] == fabrication_block
    # Content_loss replaced wholesale: stale dropped entry is gone.
    assert doc["content_loss"]["verdict"] == "pass"
    assert doc["content_loss"]["dropped_entries"] == []
    assert doc["content_loss"]["preserved_entries"][0]["entry_id"] == "work[0]:fresh1"


# ---- AC5 smoke: schema-valid + parseable ----------------------------------


def test_drift_json_round_trips_through_json_loads_in_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5 smoke: the produced file parses cleanly and the parsed dict carries
    the expected keys + types — the contract the future stats aggregator (or
    diagnostics UI in Story 4.4) consumes."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    _stage_canonical_cv_dict(tmp_path, monkeypatch, _cv_with_high_impact())
    out_root, _ = _stage(
        tmp_path,
        monkeypatch,
        cv="# CV\n\n- Shipped a TypeScript ingestion service\n",
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
    raw = (slug_dir / "package.drift.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    cl = parsed["content_loss"]
    assert isinstance(cl["verdict"], str)
    assert isinstance(cl["check_version"], str)
    assert isinstance(cl["ran_at"], str)
    assert isinstance(cl["preserved_entries"], list)
    assert isinstance(cl["dropped_entries"], list)
