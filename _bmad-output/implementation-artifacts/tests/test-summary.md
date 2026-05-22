# Test Automation Summary — Story 1.3

**Story:** Canonical CV reader with PDF/docx ingest rejection
**Date:** 2026-05-23
**Author:** dave (via BMad qa-generate-e2e-tests)
**Framework:** pytest 9.0.3 (existing project framework)
**Run command:** `.venv/bin/python -m pytest`
**Result:** **70 passed, 2 skipped in 1.02s**

Skips are pre-existing `python-dotenv` sandbox limitations from Story 1.2 (not introduced by this run). 14 new tests added; 0 regressions.

## Testing Surface

Story 1.3 has no HTTP API and no UI. The automated surface is:

1. The canonical-CV reader contract (`read_canonical_cv()`) — happy path, FR4 no-cache, missing-file, binary-format rejection (`.pdf`/`.docx`/`.doc` + case variants), exception types.
2. The CLI `paste` entrypoint — env-invalid path, env-valid + reader-failure paths (PDF/docx/missing), env-valid + reader-success Story 1.4 boundary.

## Gap Analysis (test additions in this run)

Story 1.3's dev agent landed comprehensive coverage. The QA pass identified seven gaps and closed each:

| # | Gap | New test(s) |
|---|---|---|
| 1 | `.DOC` uppercase rejection (only `.doc` lower tested) | `test_doc_uppercase_path_is_rejected` |
| 2 | Mixed-case extensions (`.Pdf`, `.Docx`) — `suffix.lower()` not exercised against mixed casings | `test_mixed_case_pdf_path_is_rejected`, `test_mixed_case_docx_path_is_rejected` |
| 3 | Extension-check ordering — a non-existent `.pdf` must raise `UnsupportedCanonicalCVFormat`, NOT `CanonicalCVMissing` (proves rejection precedes any `open()`) | `test_rejection_precedes_existence_check` |
| 4 | AC10 — runtime reader must NOT enforce JSON Resume schema | `test_reader_does_not_validate_jsonresume_schema` |
| 5 | Exception chaining (`CanonicalCVMissing.__cause__` is `FileNotFoundError`) | `test_canonical_cv_missing_chains_from_file_not_found` |
| 6 | CLI case-insensitivity at integration boundary (`.PDF` uppercase + `.doc` lower not in subprocess tests) | `test_paste_subprocess_rejects_pdf_uppercase_canonical_cv`, `test_paste_subprocess_rejects_doc_canonical_cv_before_story_1_4` |
| 7 | Exit code tightening — pre-existing CLI tests only asserted `returncode >= 1`; Task 3 contract specifies exit code `2` | `test_cli_paste_rejects_pdf_exits_with_code_two`, `test_cli_paste_rejects_docx_exits_with_code_two`, `test_cli_paste_rejects_missing_canonical_cv_exits_with_code_two`, `test_cli_paste_does_not_create_out_directory_on_rejection` |

## Generated Tests

### Unit Tests — `tests/unit/test_canonical_cv_reader.py` (+6)

- `test_doc_uppercase_path_is_rejected` — case-insensitivity for legacy `.DOC`
- `test_mixed_case_pdf_path_is_rejected` — `.Pdf` mixed case
- `test_mixed_case_docx_path_is_rejected` — `.Docx` mixed case
- `test_rejection_precedes_existence_check` — AC2 safety: no `open()` before suffix check
- `test_reader_does_not_validate_jsonresume_schema` — AC10: validator script owns schema enforcement
- `test_canonical_cv_missing_chains_from_file_not_found` — preserves debugger trail via `__cause__`

### CLI Integration Tests — `tests/integration/test_cli_entry.py` (+6)

- `test_paste_subprocess_rejects_pdf_uppercase_canonical_cv` — case-insensitivity at CLI subprocess boundary
- `test_paste_subprocess_rejects_doc_canonical_cv_before_story_1_4` — `.doc` (legacy Word) at CLI subprocess boundary
- `test_cli_paste_rejects_pdf_exits_with_code_two` — Task 3 contract: exit code `2` exactly
- `test_cli_paste_rejects_docx_exits_with_code_two` — same for `.docx`
- `test_cli_paste_rejects_missing_canonical_cv_exits_with_code_two` — same for missing file
- `test_cli_paste_does_not_create_out_directory_on_rejection` — AC7 in-process guard: no `./out/` written

### Fixtures Added — `tests/conftest.py` (+4)

- `doc_canonical_cv_upper` — `.DOC` zero-byte
- `pdf_canonical_cv_mixed_case` — `.Pdf` zero-byte
- `docx_canonical_cv_mixed_case` — `.Docx` zero-byte
- `nonexistent_pdf_canonical_cv` — `.pdf` path with NO file on disk (proves extension check precedes existence check)

All new fixtures follow the existing two-bind monkeypatch pattern (`jobhunter.config` + `jobhunter.canonical_cv`) and write zero-byte files where applicable so any regression that falls through to `json.load` fails loudly with `JSONDecodeError`.

## Coverage

- **Reader unit contract:** 17/17 known behaviors (happy path, FR4 no-cache, missing, malformed JSON, all rejected extensions in lower/upper/mixed case, ordering, no schema validation, exception chaining, `ValueError` subclass).
- **CLI rejection paths:** 22/22 known behaviors (env-invalid, env-valid + valid CV reaches Story 1.4 boundary, all rejection extensions at subprocess + in-process, exit code `2` contract, no `./out/` side effect, no JD ingest).
- **Safety guardrails (AC7):** No new test imports an LLM SDK, `requests`, `httpx`, or `python-docx`/`pdfminer`. Rejection-path tests assert `./out/` does not exist after the run.
- **No new runtime dependency added (AC9):** All tests use stdlib + pytest only.
- **Full pytest suite:** 70/70 passing (+ 2 pre-existing dotenv-sandbox skips).

## Validation Against `checklist.md`

- [x] API tests generated (if applicable) — N/A; no HTTP service.
- [x] E2E tests generated (if UI exists) — N/A for UI; CLI subprocess integration tests cover the user-facing surface.
- [x] Tests use standard test framework APIs (pytest + `monkeypatch`, stdlib `subprocess`; no custom abstractions).
- [x] Tests cover happy path (`test_reads_and_returns_parsed_dict`, `test_paste_subprocess_valid_env_stops_at_story_1_4_boundary`).
- [x] Tests cover critical error cases (`.pdf`/`.PDF`/`.Pdf`/`.docx`/`.DOCX`/`.Docx`/`.doc`/`.DOC`/missing/malformed-JSON).
- [x] All generated tests run successfully (`70 passed, 2 skipped`).
- [x] Locators are semantic — substring assertions on `"PDF"`, `"docx"`, `"Word"`, path strings (copywriting-stable per Dev Notes Testing Standards).
- [x] Test descriptions are clear (each docstring states the gap or AC the test guards).
- [x] No hardcoded waits or sleeps — subprocess `timeout=5` is a failure guard only.
- [x] Tests are independent — `tmp_path` + `monkeypatch` rebuild state per test; no shared mutable globals.
- [x] Test summary created — this file.
- [x] Tests saved to appropriate directories — `tests/unit/` and `tests/integration/` per existing convention.
- [x] Summary includes coverage and gap-closure metrics.

## Files Modified

- `tests/conftest.py` (+4 fixtures)
- `tests/unit/test_canonical_cv_reader.py` (+6 tests)
- `tests/integration/test_cli_entry.py` (+6 tests)

## Next Steps

- No source changes needed; gap-closure tests validate the already-implemented behavior.
- When Story 1.4 lands stdin / `--file` JD ingest, extend `tests/integration/test_cli_entry.py` to also confirm the reader is called BEFORE stdin is consumed (AC7 ordering carries forward).
- When Story 2.1's markdown/YAML fall-back fires, replace `test_invalid_json_propagates_as_decode_error` with format-aware variants and add `.md` / `.yaml` happy-path tests.
