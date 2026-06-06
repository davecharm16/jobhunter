"""Unit tests for `jobhunter.metadata` (Story 2.10)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from jobhunter.metadata import (
    DEFAULT_DRIFT_VERDICTS,
    PER_APP_COST_TARGET_USD,
    CallLog,
    PackageMetadata,
    build_metadata,
    format_cost,
    now_iso8601_utc,
    write_sidecar,
)


FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)
EXPECTED_TIMESTAMP = "2026-05-24T03:15:30Z"


def _sample_call(usd: str = "0.004200") -> CallLog:
    return CallLog(
        model="claude-haiku-4-5",
        input_tokens=1234,
        output_tokens=567,
        usd_cost=usd,
        purpose="tailor_cv_and_cover_letter",
    )


# --- format_cost -----------------------------------------------------------


def test_format_cost_preserves_trailing_zeros() -> None:
    assert format_cost(Decimal("0.25")) == "0.250000"


def test_format_cost_quantizes_to_six_decimal_places() -> None:
    assert format_cost(Decimal("0.0042")) == "0.004200"


def test_format_cost_rounds_to_quantum() -> None:
    assert format_cost(Decimal("0.0000001")) == "0.000000"


# --- now_iso8601_utc -------------------------------------------------------


def test_now_iso8601_utc_uses_z_suffix() -> None:
    assert now_iso8601_utc(FIXED_NOW) == EXPECTED_TIMESTAMP


def test_now_iso8601_utc_normalizes_naive_to_utc() -> None:
    naive = datetime(2026, 5, 24, 3, 15, 30)
    assert now_iso8601_utc(naive) == EXPECTED_TIMESTAMP


# --- build_metadata: defaults match AC1 verbatim --------------------------


def test_build_metadata_populates_ac1_fields_with_defaults() -> None:
    md = build_metadata(
        slug="20260524t031530z-jd",
        jd_source="paste",
        artifacts_produced=["cv", "cover_letter"],
        calls=[_sample_call()],
        now=FIXED_NOW,
    )
    assert md.slug == "20260524t031530z-jd"
    assert md.source_board == "unknown"
    assert md.jd_source == "paste"
    assert md.parsed_jd == {}
    assert md.red_flags == []
    assert md.artifacts_produced == ["cv", "cover_letter"]
    assert md.prompt_templates == {}
    assert md.drift_verdicts == DEFAULT_DRIFT_VERDICTS
    assert md.override == {"applied": False, "reason": None}
    assert md.created_at == EXPECTED_TIMESTAMP


def test_default_drift_verdicts_are_all_pending() -> None:
    assert DEFAULT_DRIFT_VERDICTS == {
        "fabrication": "pending",
        "content_loss": "pending",
        "keyword_stuffing": "pending",
    }


def test_build_metadata_drift_verdicts_default_is_a_copy_not_shared() -> None:
    """Two metadata records must not share the same drift_verdicts dict."""
    md1 = build_metadata(
        slug="a",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
    )
    md2 = build_metadata(
        slug="b",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
    )
    assert md1.drift_verdicts is not md2.drift_verdicts


# --- AC3: cost.total_usd, exceeded_per_app_target -------------------------


def test_cost_total_usd_sums_calls() -> None:
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[_sample_call("0.010000"), _sample_call("0.020000")],
        now=FIXED_NOW,
    )
    assert md.cost.total_usd == "0.030000"


def test_cost_total_usd_zero_when_no_calls() -> None:
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
    )
    assert md.cost.total_usd == "0.000000"
    assert md.cost.calls == []


def test_cost_per_app_target_defaults_to_25_cents() -> None:
    assert PER_APP_COST_TARGET_USD == Decimal("0.25")
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
    )
    assert md.cost.per_app_target_usd == "0.250000"


def test_exceeded_per_app_target_false_below_cap() -> None:
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[_sample_call("0.100000")],
        now=FIXED_NOW,
    )
    assert md.cost.exceeded_per_app_target is False


def test_exceeded_per_app_target_false_at_exact_target() -> None:
    """At-target run is not a breach (strict `>` comparison)."""
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[_sample_call("0.250000")],
        now=FIXED_NOW,
    )
    assert md.cost.exceeded_per_app_target is False
    assert md.cost.total_usd == "0.250000"


def test_exceeded_per_app_target_true_above_cap() -> None:
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[_sample_call("0.260000")],
        now=FIXED_NOW,
    )
    assert md.cost.exceeded_per_app_target is True


def test_cost_uses_decimal_not_float_for_summation() -> None:
    """0.1 + 0.2 must equal exactly 0.3 — proves Decimal arithmetic."""
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[_sample_call("0.100000"), _sample_call("0.200000")],
        now=FIXED_NOW,
    )
    assert md.cost.total_usd == "0.300000"


# --- AC2: per-call log entries -------------------------------------------


def test_call_log_has_required_fields() -> None:
    call = _sample_call()
    assert call.model == "claude-haiku-4-5"
    assert call.input_tokens == 1234
    assert call.output_tokens == 567
    assert call.usd_cost == "0.004200"
    assert call.purpose == "tailor_cv_and_cover_letter"


def test_build_metadata_appends_call_to_cost_calls() -> None:
    call = _sample_call()
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=["cv", "cover_letter"],
        calls=[call],
        now=FIXED_NOW,
    )
    assert md.cost.calls == [call]


# --- AC1 + AC5: write_sidecar atomic JSON write ---------------------------


def test_write_sidecar_emits_metadata_json(tmp_path) -> None:
    out_dir = tmp_path / "20260524t031530z-jd"
    out_dir.mkdir()
    md = build_metadata(
        slug=out_dir.name,
        jd_source="paste",
        artifacts_produced=["cv", "cover_letter"],
        calls=[_sample_call()],
        now=FIXED_NOW,
    )
    target = write_sidecar(out_dir, md)
    assert target == out_dir / "metadata.json"
    assert target.exists()


def test_write_sidecar_payload_parses_as_json_and_matches_ac1(tmp_path) -> None:
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv", "cover_letter"],
        calls=[_sample_call()],
        now=FIXED_NOW,
    )
    write_sidecar(out_dir, md)
    data = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert data["slug"] == "slug"
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
    assert data["cost"]["total_usd"] == "0.004200"
    assert data["cost"]["per_app_target_usd"] == "0.250000"
    assert data["cost"]["exceeded_per_app_target"] is False
    assert data["cost"]["calls"] == [
        {
            "model": "claude-haiku-4-5",
            "input_tokens": 1234,
            "output_tokens": 567,
            "usd_cost": "0.004200",
            "purpose": "tailor_cv_and_cover_letter",
        }
    ]
    assert data["created_at"] == EXPECTED_TIMESTAMP


def test_write_sidecar_serializes_cost_as_quoted_string(tmp_path) -> None:
    """Decimal cost MUST be a JSON string, not a bare number — float
    round-trip would silently lose precision.
    """
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=[],
        calls=[_sample_call("24.970000")],
        now=FIXED_NOW,
    )
    write_sidecar(out_dir, md)
    raw = (out_dir / "metadata.json").read_text(encoding="utf-8")
    assert '"total_usd": "24.970000"' in raw
    assert '"per_app_target_usd": "0.250000"' in raw
    assert '"usd_cost": "24.970000"' in raw


def test_write_sidecar_atomic_no_tmp_left_behind(tmp_path) -> None:
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[_sample_call()],
        now=FIXED_NOW,
    )
    write_sidecar(out_dir, md)
    assert not (out_dir / ".metadata.tmp").exists()
    assert (out_dir / "metadata.json").exists()


def test_write_sidecar_crash_during_replace_does_not_leave_metadata(
    tmp_path, monkeypatch
) -> None:
    """An OSError on rename leaves no metadata.json; AC5 still holds because
    artifacts (cv.md, cover-letter.md) were already written before the call.
    """
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[_sample_call()],
        now=FIXED_NOW,
    )

    def raise_on_replace(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("simulated crash during rename")

    import jobhunter.metadata as metadata_module

    monkeypatch.setattr(metadata_module.os, "replace", raise_on_replace)

    with pytest.raises(OSError, match="simulated crash"):
        write_sidecar(out_dir, md)

    assert not (out_dir / "metadata.json").exists()


def test_write_sidecar_overwrites_existing_metadata(tmp_path) -> None:
    """Story 2.10 has one writer; future stories may re-run — atomic replace
    must overwrite cleanly, never raise FileExistsError.
    """
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md1 = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[_sample_call("0.001000")],
        now=FIXED_NOW,
    )
    write_sidecar(out_dir, md1)
    md2 = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv", "cover_letter"],
        calls=[_sample_call("0.002000")],
        now=FIXED_NOW,
    )
    target = write_sidecar(out_dir, md2)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["artifacts_produced"] == ["cv", "cover_letter"]
    assert data["cost"]["total_usd"] == "0.002000"


def test_package_metadata_is_frozen_dataclass() -> None:
    """Match Epic 1 pattern — every public dataclass is frozen."""
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
    )
    with pytest.raises(Exception):
        md.slug = "other"  # type: ignore[misc]


# --- D1: job_title + company_name in metadata payload --------------------


def test_build_metadata_job_title_and_company_name_default_to_none() -> None:
    """D1: build_metadata defaults job_title and company_name to None."""
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
    )
    assert md.job_title is None
    assert md.company_name is None


def test_build_metadata_passes_job_title_and_company_name() -> None:
    """D1: build_metadata surfaces job_title and company_name when supplied."""
    md = build_metadata(
        slug="s",
        jd_source="paste",
        artifacts_produced=[],
        calls=[],
        now=FIXED_NOW,
        job_title="Senior Frontend Engineer",
        company_name="Stripe",
    )
    assert md.job_title == "Senior Frontend Engineer"
    assert md.company_name == "Stripe"


def test_write_sidecar_persists_job_title_and_company_name(tmp_path) -> None:
    """D1: metadata.json round-trips job_title and company_name."""
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[_sample_call()],
        now=FIXED_NOW,
        job_title="Senior Frontend Engineer",
        company_name="Stripe",
    )
    write_sidecar(out_dir, md)
    data = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert data["job_title"] == "Senior Frontend Engineer"
    assert data["company_name"] == "Stripe"


def test_write_sidecar_persists_null_job_title_and_company_name(tmp_path) -> None:
    """D1: metadata.json round-trips None job_title/company_name as JSON null."""
    out_dir = tmp_path / "slug"
    out_dir.mkdir()
    md = build_metadata(
        slug="slug",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[_sample_call()],
        now=FIXED_NOW,
    )
    write_sidecar(out_dir, md)
    data = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert data["job_title"] is None
    assert data["company_name"] is None
