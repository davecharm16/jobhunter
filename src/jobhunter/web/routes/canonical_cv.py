"""Canonical-CV editor routes (Story 2.13).

`GET /api/canonical-cv` invokes `jobhunter.canonical_cv.read_canonical_cv()` on
every request — the §2 read-fresh contract means out-of-band edits to the file
are visible on the next request with no caching layer.

`PUT /api/canonical-cv` validates the request body against the vendored
JSON Resume v1.0.0 schema (which Story 2.1 extended with `tags` + `highImpact`),
then writes atomically via the tmp-sibling + `os.replace()` idiom shared with
Stories 1.5 and 2.10. Validation failures return 422 with JSON Pointer paths
and the file on disk is unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from jobhunter import config as config_module
from jobhunter.canonical_cv import (
    CanonicalCVMalformed,
    CanonicalCVMissing,
    UnsupportedCanonicalCVFormat,
    read_canonical_cv,
)
from jobhunter.config import PROJECT_ROOT, VENDORED_JSONRESUME_SCHEMA_PATH


router = APIRouter()


def _json_pointer(path_parts: Any) -> str:
    """Render a jsonschema absolute_path deque as a JSON Pointer string."""
    parts = list(path_parts)
    if not parts:
        return "/"
    return "/" + "/".join(str(p) for p in parts)


def _collect_validation_errors(document: Any) -> list[dict[str, str]]:
    with open(VENDORED_JSONRESUME_SCHEMA_PATH, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    ValidatorCls = validator_for(schema)
    ValidatorCls.check_schema(schema)
    validator = ValidatorCls(schema, format_checker=FormatChecker())
    return [
        {"path": _json_pointer(error.absolute_path), "message": error.message}
        for error in validator.iter_errors(document)
    ]


def _relative_path(path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


@router.get("/api/canonical-cv")
def get_canonical_cv() -> dict[str, Any]:
    try:
        return read_canonical_cv()
    except CanonicalCVMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedCanonicalCVFormat as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except CanonicalCVMalformed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/api/canonical-cv")
def put_canonical_cv(payload: dict[str, Any]) -> JSONResponse:
    errors = _collect_validation_errors(payload)
    if errors:
        return JSONResponse(
            status_code=422,
            content={"detail": "schema_validation_failed", "errors": errors},
        )

    target = config_module.CANONICAL_CV_PATH
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp_path, target)
    except OSError as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to write canonical CV: {exc}") from exc

    return JSONResponse(
        status_code=200,
        content={"saved": True, "path": _relative_path(target)},
    )
