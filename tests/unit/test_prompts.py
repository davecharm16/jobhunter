"""Unit tests for `jobhunter.prompts` (Story 2.9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobhunter.prompts import (
    PromptTemplate,
    PromptTemplateAmbiguous,
    PromptTemplateMissing,
    load_prompt,
)


def _write(dir_path: Path, name: str, content: str) -> Path:
    path = dir_path / name
    path.write_text(content, encoding="utf-8")
    return path


# --- AC1: filename version extraction --------------------------------------


def test_load_prompt_extracts_version_from_filename(tmp_path: Path) -> None:
    _write(tmp_path, "cv.v3.md", "tailor cv v3\n")
    template = load_prompt("cv", prompts_dir=tmp_path)
    assert template.version == "v3"
    assert template.name == "cv"


def test_load_prompt_returns_file_content_verbatim(tmp_path: Path) -> None:
    payload = "you are an assistant.\n\nproduce two artifacts.\n"
    written = _write(tmp_path, "cv.v1.md", payload)
    template = load_prompt("cv", prompts_dir=tmp_path)
    assert template.content == payload
    assert template.path == written


def test_load_prompt_returns_frozen_dataclass(tmp_path: Path) -> None:
    _write(tmp_path, "cv.v1.md", "hello\n")
    template = load_prompt("cv", prompts_dir=tmp_path)
    assert isinstance(template, PromptTemplate)
    with pytest.raises((AttributeError, Exception)):
        template.version = "v9"  # type: ignore[misc]


# --- AC1: highest version wins ---------------------------------------------


def test_load_prompt_picks_highest_version_when_multiple_exist(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "cv.v1.md", "v1\n")
    _write(tmp_path, "cv.v2.md", "v2\n")
    _write(tmp_path, "cv.v10.md", "v10\n")
    template = load_prompt("cv", prompts_dir=tmp_path)
    assert template.version == "v10"
    assert template.content == "v10\n"


def test_load_prompt_compares_versions_numerically_not_lexically(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "cv.v2.md", "v2\n")
    _write(tmp_path, "cv.v11.md", "v11\n")
    template = load_prompt("cv", prompts_dir=tmp_path)
    assert template.version == "v11"


# --- AC2: missing file raises -----------------------------------------------


def test_load_prompt_raises_missing_when_directory_empty(tmp_path: Path) -> None:
    with pytest.raises(PromptTemplateMissing, match="no prompt template"):
        load_prompt("cv", prompts_dir=tmp_path)


def test_load_prompt_raises_missing_when_directory_does_not_exist(
    tmp_path: Path,
) -> None:
    nonexistent = tmp_path / "does-not-exist"
    with pytest.raises(PromptTemplateMissing, match="does not exist"):
        load_prompt("cv", prompts_dir=nonexistent)


def test_load_prompt_raises_missing_when_other_artifacts_present(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "cover_letter.v1.md", "x\n")
    with pytest.raises(PromptTemplateMissing):
        load_prompt("cv", prompts_dir=tmp_path)


def test_prompt_template_missing_is_a_filenotfounderror() -> None:
    assert issubclass(PromptTemplateMissing, FileNotFoundError)


# --- AC2: ambiguous version --------------------------------------------------


def test_load_prompt_raises_ambiguous_when_two_files_share_version(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "cv.v1.md", "first\n")
    # Build a second file with the same numeric version via a path that the
    # parser would still match (it would not — there is only one filename per
    # version on disk). Simulate by directly using the same filename twice.
    # Instead, simulate via two distinct files mapping to the same version
    # number using `cv.v01.md` and `cv.v1.md` (both parse to int 1).
    _write(tmp_path, "cv.v01.md", "second\n")
    with pytest.raises(PromptTemplateAmbiguous, match="v1"):
        load_prompt("cv", prompts_dir=tmp_path)


def test_prompt_template_ambiguous_is_valueerror() -> None:
    assert issubclass(PromptTemplateAmbiguous, ValueError)


# --- Read-fresh contract ----------------------------------------------------


def test_load_prompt_reads_fresh_from_disk_on_every_call(tmp_path: Path) -> None:
    path = _write(tmp_path, "cv.v1.md", "first\n")
    first = load_prompt("cv", prompts_dir=tmp_path)
    assert first.content == "first\n"
    path.write_text("second\n", encoding="utf-8")
    second = load_prompt("cv", prompts_dir=tmp_path)
    assert second.content == "second\n"


# --- Filename filtering ----------------------------------------------------


def test_load_prompt_ignores_files_without_version_suffix(tmp_path: Path) -> None:
    _write(tmp_path, "cv.md", "no version\n")
    with pytest.raises(PromptTemplateMissing):
        load_prompt("cv", prompts_dir=tmp_path)


def test_load_prompt_does_not_match_artifact_prefix_collision(
    tmp_path: Path,
) -> None:
    """`cv` must not match `cv_extras.v1.md` — the dot separator is required."""
    _write(tmp_path, "cv_extras.v1.md", "x\n")
    with pytest.raises(PromptTemplateMissing):
        load_prompt("cv", prompts_dir=tmp_path)


# --- Smoke: real prompts/ on disk ------------------------------------------


def test_load_prompt_finds_committed_cv_v1_template() -> None:
    from jobhunter.config import PROJECT_ROOT

    template = load_prompt("cv", prompts_dir=PROJECT_ROOT / "prompts")
    assert template.version == "v1"
    assert "emit_tailored_artifacts" in template.content


def test_load_prompt_finds_committed_cover_letter_v1_template() -> None:
    from jobhunter.config import PROJECT_ROOT

    template = load_prompt(
        "cover_letter", prompts_dir=PROJECT_ROOT / "prompts"
    )
    assert template.version == "v1"
    assert "emit_tailored_artifacts" in template.content


def test_committed_cv_template_matches_baked_in_system_prompt() -> None:
    """v1 zero-behavioral-change contract: extracted file must equal SYSTEM_PROMPT."""
    from jobhunter.config import PROJECT_ROOT
    from jobhunter.llm_client import SYSTEM_PROMPT

    template = load_prompt("cv", prompts_dir=PROJECT_ROOT / "prompts")
    assert template.content == SYSTEM_PROMPT
