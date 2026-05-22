"""Sanity tests for the committed canonical-cv.json sample (AC #4, #5).

These tests pin the shape Task 3 of story 1.1 requires:
  - ≥ 2 work entries with `highlights[]`
  - ≥ 3 skills with `keywords[]`
  - ≥ 1 project with `highlights[]`
  - ≥ 1 education entry
  - `basics.email` present and well-formed

Schema validation is exercised end-to-end by the validator-script integration
test; these tests catch shape regressions without invoking the validator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobhunter.config import CANONICAL_CV_PATH


@pytest.fixture(scope="module")
def sample_cv() -> dict:
    with open(CANONICAL_CV_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_basics_block_present_and_has_email(sample_cv: dict) -> None:
    assert "basics" in sample_cv
    assert "email" in sample_cv["basics"]
    assert "@" in sample_cv["basics"]["email"]


def test_at_least_two_work_entries_with_highlights(sample_cv: dict) -> None:
    work = sample_cv.get("work", [])
    assert len(work) >= 2, f"expected ≥ 2 work entries, found {len(work)}"
    for entry in work:
        assert entry.get("highlights"), (
            f"work entry {entry.get('name')!r} missing highlights"
        )


def test_at_least_three_skills_with_keywords(sample_cv: dict) -> None:
    skills = sample_cv.get("skills", [])
    assert len(skills) >= 3, f"expected ≥ 3 skills, found {len(skills)}"
    for skill in skills:
        assert skill.get("keywords"), (
            f"skill {skill.get('name')!r} missing keywords"
        )


def test_at_least_one_project_with_highlights(sample_cv: dict) -> None:
    projects = sample_cv.get("projects", [])
    assert len(projects) >= 1
    assert projects[0].get("highlights")


def test_at_least_one_education_entry(sample_cv: dict) -> None:
    education = sample_cv.get("education", [])
    assert len(education) >= 1
