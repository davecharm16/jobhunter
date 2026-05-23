"""Unit tests for Story 2.1: canonical-CV tags, highImpact flag, malformed-doc handling.

AC1: tags round-trip on every read, no re-import step; the bundled sample uses them.
AC2: highImpact entries surface via the `high_impact_entries()` projection (FR3).
AC3: malformed documents raise `CanonicalCVMalformed` with a JSON Pointer path;
     absent `tags` stays absent — no silent coercion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from jobhunter.canonical_cv import (
    CanonicalCVMalformed,
    high_impact_entries,
    read_canonical_cv,
)
from jobhunter.config import VENDORED_JSONRESUME_SCHEMA_PATH


SAMPLE_WITH_EXTENSIONS_REL = Path("samples") / "canonical-cv-with-extensions.json"


def _write_cv(target: Path, document: dict) -> None:
    target.write_text(json.dumps(document), encoding="utf-8")


# ---------- AC1: tags ----------------------------------------------------------


def test_tags_round_trip_on_work_entries(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["tags"] = ["node", "typescript", "fintech"]
    _write_cv(tmp_canonical_cv, doc)

    result = read_canonical_cv()

    assert result["work"][0]["tags"] == ["node", "typescript", "fintech"]


def test_tags_round_trip_on_skills_entries(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["skills"][0]["tags"] = ["backend", "api"]
    _write_cv(tmp_canonical_cv, doc)

    result = read_canonical_cv()

    assert result["skills"][0]["tags"] == ["backend", "api"]


def test_tags_round_trip_on_projects_entries(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["projects"][0]["tags"] = ["llm", "automation"]
    _write_cv(tmp_canonical_cv, doc)

    result = read_canonical_cv()

    assert result["projects"][0]["tags"] == ["llm", "automation"]


def test_absent_tags_means_absent_not_empty(tmp_canonical_cv: Path) -> None:
    """AC3: absent `tags` array must NOT be coerced to `[]` or any sentinel."""
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    assert "tags" not in doc["work"][0]
    _write_cv(tmp_canonical_cv, doc)

    result = read_canonical_cv()

    assert "tags" not in result["work"][0]


def test_tags_re_read_picks_up_edits_on_each_call(tmp_canonical_cv: Path) -> None:
    """AC1: no re-import step — tags edits land on the very next read."""
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["tags"] = ["initial"]
    _write_cv(tmp_canonical_cv, doc)
    first = read_canonical_cv()
    assert first["work"][0]["tags"] == ["initial"]

    doc["work"][0]["tags"] = ["updated", "fresh"]
    _write_cv(tmp_canonical_cv, doc)
    second = read_canonical_cv()
    assert second["work"][0]["tags"] == ["updated", "fresh"]


def test_tags_must_be_array_of_strings(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["tags"] = "not-an-array"
    _write_cv(tmp_canonical_cv, doc)

    with pytest.raises(CanonicalCVMalformed):
        read_canonical_cv()


def test_bundled_sample_validates_against_schema(project_root: Path) -> None:
    """AC1: the committed `samples/canonical-cv-with-extensions.json` must validate."""
    sample = json.loads(
        (project_root / SAMPLE_WITH_EXTENSIONS_REL).read_text(encoding="utf-8")
    )
    schema = json.loads(
        VENDORED_JSONRESUME_SCHEMA_PATH.read_text(encoding="utf-8")
    )
    ValidatorCls = validator_for(schema)
    ValidatorCls.check_schema(schema)
    validator = ValidatorCls(schema, format_checker=FormatChecker())
    errors = list(validator.iter_errors(sample))

    assert errors == [], (
        "bundled extensions sample failed schema validation:\n"
        + "\n".join(f"  at {list(e.absolute_path)}: {e.message}" for e in errors)
    )


def test_bundled_sample_demonstrates_tags_and_high_impact(project_root: Path) -> None:
    """AC1: the sample must actually show tags + highImpact in use."""
    sample = json.loads(
        (project_root / SAMPLE_WITH_EXTENSIONS_REL).read_text(encoding="utf-8")
    )

    work_tags = [e.get("tags") for e in sample.get("work", []) if e.get("tags")]
    skills_tags = [e.get("tags") for e in sample.get("skills", []) if e.get("tags")]
    projects_tags = [e.get("tags") for e in sample.get("projects", []) if e.get("tags")]
    assert work_tags and skills_tags and projects_tags

    flagged = [
        e
        for section in ("work", "skills", "projects")
        for e in sample.get(section, [])
        if e.get("highImpact") is True
    ]
    assert len(flagged) >= 1


# ---------- AC2: high_impact_entries projection --------------------------------


def test_high_impact_entries_surfaces_flagged_work(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["highImpact"] = True
    _write_cv(tmp_canonical_cv, doc)
    cv = read_canonical_cv()

    flagged = high_impact_entries(cv)

    assert len(flagged) == 1
    assert flagged[0]["_section"] == "work"
    assert flagged[0]["name"] == "Acme"


def test_high_impact_entries_surfaces_across_sections(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["highImpact"] = True
    doc["skills"][0]["highImpact"] = True
    doc["projects"][0]["highImpact"] = True
    _write_cv(tmp_canonical_cv, doc)
    cv = read_canonical_cv()

    flagged = high_impact_entries(cv)
    sections = {e["_section"] for e in flagged}

    assert sections == {"work", "skills", "projects"}
    assert len(flagged) == 3


def test_high_impact_entries_excludes_unflagged(tmp_canonical_cv: Path) -> None:
    """Entries with no highImpact field default to off — they are excluded."""
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    assert "highImpact" not in doc["work"][0]
    _write_cv(tmp_canonical_cv, doc)
    cv = read_canonical_cv()

    assert high_impact_entries(cv) == []


def test_high_impact_entries_excludes_explicit_false(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["highImpact"] = False
    doc["skills"][0]["highImpact"] = False
    _write_cv(tmp_canonical_cv, doc)
    cv = read_canonical_cv()

    assert high_impact_entries(cv) == []


def test_high_impact_entries_does_not_re_read_disk(
    tmp_canonical_cv: Path,
) -> None:
    """`high_impact_entries` is a pure projection — it must not touch the disk."""
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["highImpact"] = True
    _write_cv(tmp_canonical_cv, doc)
    cv = read_canonical_cv()

    tmp_canonical_cv.unlink()

    flagged = high_impact_entries(cv)
    assert len(flagged) == 1


def test_high_impact_entries_preserves_full_entry_fields(
    tmp_canonical_cv: Path,
) -> None:
    """The projection annotates `_section` but keeps every original field intact."""
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["highImpact"] = True
    doc["work"][0]["tags"] = ["fintech"]
    _write_cv(tmp_canonical_cv, doc)
    cv = read_canonical_cv()

    flagged = high_impact_entries(cv)[0]

    assert flagged["_section"] == "work"
    assert flagged["name"] == "Acme"
    assert flagged["position"] == "Engineer"
    assert flagged["highlights"] == ["Shipped a thing"]
    assert flagged["tags"] == ["fintech"]
    assert flagged["highImpact"] is True


def test_high_impact_must_be_boolean(tmp_canonical_cv: Path) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["highImpact"] = "yes"
    _write_cv(tmp_canonical_cv, doc)

    with pytest.raises(CanonicalCVMalformed):
        read_canonical_cv()


def test_high_impact_entries_on_empty_cv() -> None:
    assert high_impact_entries({}) == []


# ---------- AC3: malformed-doc handling ----------------------------------------


def test_canonical_cv_malformed_subclasses_value_error() -> None:
    assert issubclass(CanonicalCVMalformed, ValueError)


def test_malformed_doc_raises_canonical_cv_malformed(
    tmp_canonical_cv: Path,
) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["basics"]["name"] = 42
    _write_cv(tmp_canonical_cv, doc)

    with pytest.raises(CanonicalCVMalformed):
        read_canonical_cv()


def test_malformed_error_message_includes_json_pointer(
    tmp_canonical_cv: Path,
) -> None:
    """AC3: the error must name the offending JSON Pointer path."""
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["basics"]["name"] = 42
    _write_cv(tmp_canonical_cv, doc)

    with pytest.raises(CanonicalCVMalformed) as exc_info:
        read_canonical_cv()

    assert "/basics/name" in str(exc_info.value)


def test_malformed_error_message_includes_path_for_nested_entry(
    tmp_canonical_cv: Path,
) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["startDate"] = "not-a-date"
    _write_cv(tmp_canonical_cv, doc)

    with pytest.raises(CanonicalCVMalformed) as exc_info:
        read_canonical_cv()

    assert "/work/0/startDate" in str(exc_info.value)


def test_validation_passes_for_pure_jsonresume_with_no_extensions(
    tmp_canonical_cv: Path,
) -> None:
    """Extension overlay is additive — pure JSON Resume v1.0.0 must still validate."""
    result = read_canonical_cv()
    assert result["basics"]["name"] == "Test Author"


def test_validation_passes_with_extensions_on_all_three_sections(
    tmp_canonical_cv: Path,
) -> None:
    doc = json.loads(tmp_canonical_cv.read_text(encoding="utf-8"))
    doc["work"][0]["tags"] = ["a"]
    doc["work"][0]["highImpact"] = True
    doc["skills"][0]["tags"] = ["b"]
    doc["skills"][0]["highImpact"] = False
    doc["projects"][0]["tags"] = ["c"]
    doc["projects"][0]["highImpact"] = True
    _write_cv(tmp_canonical_cv, doc)

    result = read_canonical_cv()

    assert result["work"][0]["tags"] == ["a"]
    assert result["skills"][0]["highImpact"] is False
    assert result["projects"][0]["highImpact"] is True
