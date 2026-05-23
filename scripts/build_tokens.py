#!/usr/bin/env python3
"""Emit the frontend design-tokens TS module from design.md frontmatter.

Single source of truth: `design_guidelines/stitch-export/design.md`. The YAML
frontmatter at the top of that file defines colors, typography, rounded, and
spacing scales. This script parses the frontmatter without a YAML dependency
(simple `key: value` plus 2-space nested entries) and writes a TypeScript
module the Tailwind config consumes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_MD = PROJECT_ROOT / "design_guidelines" / "stitch-export" / "design.md"
TOKENS_TS = (
    PROJECT_ROOT
    / "src"
    / "jobhunter"
    / "web"
    / "frontend"
    / "src"
    / "design-tokens.ts"
)


def _extract_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        raise RuntimeError("design.md is missing the leading `---` frontmatter fence")
    end = text.find("\n---", 3)
    if end < 0:
        raise RuntimeError("design.md frontmatter is not closed by `---`")
    return text[3:end].strip()


def _parse_frontmatter(block: str) -> dict[str, object]:
    """Minimal YAML parser: 2-space nesting, scalar leaves only."""
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, root)]

    for raw_line in block.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, value = raw_line.strip().partition(":")
        key = key.strip()
        value = value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise RuntimeError(f"frontmatter indent error near {raw_line!r}")
        parent = stack[-1][1]

        if value == "":
            child: dict[str, object] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _unquote(value)

    return root


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def main() -> int:
    text = DESIGN_MD.read_text(encoding="utf-8")
    block = _extract_frontmatter(text)
    tokens = _parse_frontmatter(block)

    for required in ("colors", "typography", "rounded", "spacing"):
        if required not in tokens:
            raise RuntimeError(f"design.md frontmatter is missing `{required}`")

    body = json.dumps(tokens, indent=2, sort_keys=True)
    out = (
        "// Generated from design_guidelines/stitch-export/design.md by\n"
        "// scripts/build_tokens.py. Do not edit by hand; re-run the script.\n"
        f"export const tokens = {body} as const;\n"
        "export type Tokens = typeof tokens;\n"
    )
    TOKENS_TS.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_TS.write_text(out, encoding="utf-8")
    print(f"wrote {TOKENS_TS.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
