"""Top-level configuration constants.

`CANONICAL_CV_PATH` is the single source of truth for where the canonical CV
lives. All code that loads the canonical CV must go through
`jobhunter.canonical_cv.read_canonical_cv`, which reads this constant.
"""

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

CANONICAL_CV_PATH: Path = PROJECT_ROOT / "canonical-cv.json"

VENDORED_JSONRESUME_SCHEMA_PATH: Path = (
    PROJECT_ROOT / "schemas" / "jsonresume-v1.0.0.json"
)

CONFIG_YAML_PATH: Path = PROJECT_ROOT / "config.yaml"
