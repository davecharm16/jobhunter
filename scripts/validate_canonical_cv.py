#!/usr/bin/env python3
"""Validate canonical-cv.json against the vendored JSON Resume v1.0.0 schema.

Offline-safe: reads the vendored schema from `schemas/jsonresume-v1.0.0.json`
and never touches the network. Exits 0 on success, non-zero with a
human-readable error on failure.
"""

import json
import sys
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from jobhunter.config import CANONICAL_CV_PATH, VENDORED_JSONRESUME_SCHEMA_PATH


def _load_json(path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    if not VENDORED_JSONRESUME_SCHEMA_PATH.exists():
        sys.stderr.write(
            f"error: vendored schema not found at {VENDORED_JSONRESUME_SCHEMA_PATH}\n"
        )
        return 2

    if not CANONICAL_CV_PATH.exists():
        sys.stderr.write(
            f"error: canonical CV not found at {CANONICAL_CV_PATH}\n"
        )
        return 2

    schema = _load_json(VENDORED_JSONRESUME_SCHEMA_PATH)
    instance = _load_json(CANONICAL_CV_PATH)

    # JSON Resume v1.0.0 declares draft-04; pick the matching validator class
    # instead of hard-coding Draft7Validator so future schema upgrades don't
    # silently drift.
    ValidatorCls = validator_for(schema)
    ValidatorCls.check_schema(schema)
    validator = ValidatorCls(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))

    if not errors:
        print(f"ok: {CANONICAL_CV_PATH} validates against JSON Resume v1.0.0")
        return 0

    sys.stderr.write(
        f"error: {CANONICAL_CV_PATH} failed JSON Resume v1.0.0 validation "
        f"({len(errors)} issue(s)):\n"
    )
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        sys.stderr.write(f"  - at {loc}: {err.message}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
