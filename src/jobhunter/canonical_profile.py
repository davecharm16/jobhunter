"""Condensed canonical-CV projection for the external scan engine's ranking.

Pure function — no I/O. The scan prompt embeds this so Claude can judge fit
without shipping the entire CV. Kept small to bound prompt size."""

from typing import Any

_MAX_SKILLS = 30
_MAX_TITLES = 8


def build_canonical_profile(cv: dict[str, Any]) -> dict[str, Any]:
    basics = cv.get("basics") or {}
    skills = [
        s.get("name", "")
        for s in (cv.get("skills") or [])
        if isinstance(s, dict) and s.get("name")
    ][:_MAX_SKILLS]
    titles = []
    for w in (cv.get("work") or [])[:_MAX_TITLES]:
        if not isinstance(w, dict):
            continue
        position = w.get("position", "")
        company = w.get("name", "")
        if position or company:
            titles.append(f"{position} @ {company}".strip(" @"))
    return {
        "name": basics.get("name", ""),
        "label": basics.get("label", ""),
        "summary": basics.get("summary", ""),
        "skills": skills,
        "recent_titles": titles,
    }


__all__ = ["build_canonical_profile"]
