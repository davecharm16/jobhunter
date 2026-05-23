"""Per-board artifact-set selector (Story 2.8).

Given the `source_board` produced by the Story 2.4 classifier, decide which
artifacts a pipeline run should produce. v1 ships three valid sets:
`{cv, cover_letter}`, `{cv, upwork_proposal}`, and the union of both. An
explicit override (from the request body's `metadata.artifacts_override`)
bypasses the per-board default and is recorded implicitly via the resolved
list landing in the metadata sidecar's `artifacts_produced` field.

The selector is pure — no I/O, no LLM. Unknown artifact names or empty
override lists raise `ArtifactSelectionInvalid`. Unknown source boards
fall back to the `other` default rather than raising so a misclassified
JD never blocks the pipeline.
"""

from __future__ import annotations


__all__ = [
    "ALLOWED_ARTIFACTS",
    "ArtifactSelectionInvalid",
    "DEFAULT_BY_BOARD",
    "select",
]


ALLOWED_ARTIFACTS: frozenset[str] = frozenset(
    {"cv", "cover_letter", "upwork_proposal"}
)


DEFAULT_BY_BOARD: dict[str, list[str]] = {
    "upwork": ["cv", "upwork_proposal"],
    "linkedin": ["cv", "cover_letter"],
    "onlinejobs_ph": ["cv", "cover_letter"],
    "other": ["cv", "cover_letter"],
}


class ArtifactSelectionInvalid(ValueError):
    """An explicit override contains an unknown artifact name or is empty."""


def select(
    source_board: str,
    *,
    explicit_override: list[str] | None = None,
) -> list[str]:
    """Return the artifact set for *source_board*, honoring *explicit_override*."""
    if explicit_override is not None:
        if not explicit_override:
            raise ArtifactSelectionInvalid(
                "artifacts_override must not be empty"
            )
        unknown = [name for name in explicit_override if name not in ALLOWED_ARTIFACTS]
        if unknown:
            raise ArtifactSelectionInvalid(
                f"artifacts_override contains unknown names: {unknown!r}; "
                f"allowed: {sorted(ALLOWED_ARTIFACTS)}"
            )
        return list(explicit_override)

    default = DEFAULT_BY_BOARD.get(source_board) or DEFAULT_BY_BOARD["other"]
    return list(default)
