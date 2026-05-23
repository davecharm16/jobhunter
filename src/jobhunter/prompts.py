"""Versioned prompt-template loader (Story 2.9).

Prompt files live at `<PROJECT_ROOT>/prompts/<artifact>.v<N>.md`. The version
string is parsed from the filename (no frontmatter) and surfaced on the
returned `PromptTemplate` so the metadata writer (Story 2.10) can record
which template version produced each artifact. Files are re-read on every
call — no caching — mirroring the canonical-CV reader contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jobhunter.config import PROJECT_ROOT


__all__ = [
    "PROMPTS_DIR",
    "PromptTemplate",
    "PromptTemplateAmbiguous",
    "PromptTemplateMissing",
    "load_prompt",
]


PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"

_VERSION_PATTERN = re.compile(r"\.v(\d+)\.md\Z")


class PromptTemplateMissing(FileNotFoundError):
    """Raised when no `<artifact>.v*.md` file exists in the prompts directory."""


class PromptTemplateAmbiguous(ValueError):
    """Raised when multiple files for the same artifact share a version number."""


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    content: str
    path: Path


def load_prompt(
    artifact: str, *, prompts_dir: Path | None = None
) -> PromptTemplate:
    """Load the highest-version template for *artifact* from *prompts_dir*."""
    directory = prompts_dir if prompts_dir is not None else PROMPTS_DIR
    if not directory.is_dir():
        raise PromptTemplateMissing(
            f"prompts directory does not exist: {directory}"
        )

    candidates: dict[int, Path] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if not name.startswith(f"{artifact}."):
            continue
        match = _VERSION_PATTERN.search(name)
        if match is None:
            continue
        version_num = int(match.group(1))
        if version_num in candidates:
            raise PromptTemplateAmbiguous(
                f"multiple templates for '{artifact}' share version "
                f"v{version_num}: {candidates[version_num].name}, {name}"
            )
        candidates[version_num] = path

    if not candidates:
        raise PromptTemplateMissing(
            f"no prompt template found for '{artifact}' in {directory} "
            f"(expected a file matching '{artifact}.v<N>.md')"
        )

    chosen_version = max(candidates)
    chosen_path = candidates[chosen_version]
    return PromptTemplate(
        name=artifact,
        version=f"v{chosen_version}",
        content=chosen_path.read_text(encoding="utf-8"),
        path=chosen_path,
    )
