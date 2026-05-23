# Test Automation Summary — Story 1.5

**Story:** Single tailoring LLM call writes tailored CV + cover letter to `./out/<slug>/`
**Date:** 2026-05-23
**Author:** dave (via BMad qa-generate-e2e-tests)
**Framework:** pytest 8.x (existing project framework; `pyproject.toml` `[tool.pytest.ini_options]`)
**Run command:** `PYTHONPATH=. .venv/bin/pytest tests/`
**Result:** **173 passed, 1 skipped in 9.43s**

Baseline before this QA pass: 155 passed / 1 skipped. The QA pass added **18 new test IDs** (5 integration + 13 unit, counting parametrized cases) to close coverage gaps against the 13 ACs. The single skip is the pre-existing `python-dotenv` sandbox limitation from Story 1.2 — not introduced by this run, and zero regressions against the baseline.

## Approach

Story 1.5 already shipped with a thorough test suite from the dev pass (`tests/unit/test_slug.py`, `tests/unit/test_spend_tracker.py`, `tests/unit/test_llm_client.py`, `tests/integration/test_paste_tailoring.py`). This QA pass audited the existing tests against all 13 ACs and added regression guards for contract details that were verified by behavior but not pinned by an explicit assertion. **No real LLM endpoint is reached** — subprocess tests install a deterministic stub via `_isolated_cli_env_with_fake_llm`; in-process tests inject via the `llm_tailor=` seam in `run_tailoring()`.

## Gap Analysis (test additions in this run)

| # | AC | Gap | New tests |
|---|---|---|---|
| 1 | AC3 | Cap-exceeded stderr asserted only `$25.00` — current==cap meant a sloppy formatter echoing the cap twice would pass | `test_paste_subprocess_cap_exceeded_stderr_names_current_and_cap_separately`, `test_paste_subprocess_cap_exceeded_with_distinct_current_and_cap` |
| 2 | AC5 | No test for `.tmp/` dir cleanup after a disk failure mid-write | `test_run_tailoring_cleans_up_tmp_dir_when_artifact_write_fails` |
| 3 | AC6 | Existing covered `cv_markdown` missing + `cover_letter_markdown` whitespace; missing the symmetric cases | `test_tailor_raises_response_invalid_when_cover_letter_missing`, `test_tailor_raises_response_invalid_when_cv_markdown_empty`, `test_tailor_raises_response_invalid_when_cv_markdown_is_not_a_string` |
| 4 | AC7 | `runtime_config` lacked direct tests for `LLM_CALL_TIMEOUT_SECONDS` loading, validation, and default | `test_load_runtime_config_defaults_timeout_when_env_unset`, `test_load_runtime_config_reads_positive_timeout_override`, `test_load_runtime_config_reads_fractional_timeout`, `test_load_runtime_config_rejects_non_numeric_timeout` (×4), `test_load_runtime_config_rejects_non_positive_timeout` (×3) |
| 5 | AC7 | Existing tests pinned timeout at SDK level + invalid-env at subprocess level — gap was the end-to-end wiring | `test_runtime_config_passes_custom_timeout_into_tailoring_call` |
| 6 | AC12 | `.gitignore` was a manifest assertion only — no test prevented an accidental removal of `out/` or `.cost-ledger.json` | `test_gitignore_excludes_cost_ledger_and_out_directory` |

## Generated Tests

### Unit — `tests/unit/test_runtime_config.py` (+5 names, 9 IDs counting parametrize)

- `test_load_runtime_config_defaults_timeout_when_env_unset` — AC7 default
- `test_load_runtime_config_reads_positive_timeout_override` — AC7 positive int
- `test_load_runtime_config_reads_fractional_timeout` — AC7 positive float
- `test_load_runtime_config_rejects_non_numeric_timeout` — parametrized × 4 (`"abc"`, `"not-a-number"`, `"1.2.3"`, `"12s"`)
- `test_load_runtime_config_rejects_non_positive_timeout` — parametrized × 3 (`"0"`, `"-1"`, `"-0.5"`)

### Unit — `tests/unit/test_llm_client.py` (+3)

- `test_tailor_raises_response_invalid_when_cover_letter_missing` — AC6 missing field
- `test_tailor_raises_response_invalid_when_cv_markdown_empty` — AC6 whitespace `cv_markdown`
- `test_tailor_raises_response_invalid_when_cv_markdown_is_not_a_string` — AC6 non-string field

### Integration — `tests/integration/test_paste_tailoring.py` (+4)

- `test_paste_subprocess_cap_exceeded_stderr_names_current_and_cap_separately` — AC3 at-cap boundary
- `test_paste_subprocess_cap_exceeded_with_distinct_current_and_cap` — AC3 above-cap, distinct values
- `test_run_tailoring_cleans_up_tmp_dir_when_artifact_write_fails` — AC5 `.tmp/` cleanup
- `test_runtime_config_passes_custom_timeout_into_tailoring_call` — AC7 end-to-end wiring

### Integration — `tests/integration/test_paste_jd_ingest.py` (+1)

- `test_gitignore_excludes_cost_ledger_and_out_directory` — AC12 `.gitignore` regression guard

## Coverage by AC

| AC | Subject | Tests |
|----|---------|-------|
| AC1 | Happy-path artifact write | ✅ Multiple (subprocess + in-process; stdin + `--file`) |
| AC2 | Slug shape + deterministic + collision refusal | ✅ 11 unit + 2 integration |
| AC3 | Cap pre-check non-bypassable + stderr names both numbers | ✅ Strengthened in this pass |
| AC4 | Per-request token + cost logging (atomic ledger) | ✅ 12 unit + 1 integration |
| AC5 | Atomic artifact write on LLM failure + `.tmp/` cleanup | ✅ Closed disk-failure path in this pass |
| AC6 | LLM response validation (missing/empty/non-string) | ✅ Closed symmetric variants in this pass |
| AC7 | Per-call timeout (env + default + validation + wiring) | ✅ Closed runtime-config + wiring in this pass |
| AC8 | No HTTP traffic to job boards (source-grep guard) | ✅ 1 integration test |
| AC9 | Canonical CV untouched (mtime + sha256 snapshot) | ✅ 1 integration test |
| AC10 | Gate ordering env → CV → JD → cap → LLM → write | ✅ Inherited Stories 1.2–1.4 chain + 1 new |
| AC11 | Single new runtime dep (`anthropic`) + forbidden imports | ✅ 2 integration tests |
| AC12 | README / DECISIONS / `.gitignore` | ✅ Closed `.gitignore` guard in this pass |
| AC13 | Test-coverage meta-contract | ✅ Satisfied by all of the above |

## No Source-Code Changes

The dev pass already implements the contract correctly. All additions are pure
gap-closure tests that validate already-implemented behavior and prevent future
regressions.

## Validation Against `checklist.md`

- [x] API tests generated (if applicable) — N/A; this is a CLI app, no HTTP API surface (a fetch surface lands in Epic 2).
- [x] E2E tests generated (if UI exists) — N/A for UI; CLI subprocess + in-process integration tests cover the user-facing surface end-to-end.
- [x] Tests use standard test framework APIs — pytest + `monkeypatch` + `tmp_path` + `pytest.parametrize`. Stdlib `subprocess`, `pathlib`, `decimal`, `json`.
- [x] Tests cover happy path — AC1 covered with multiple subprocess + in-process variants for stdin and `--file`.
- [x] Tests cover critical error cases — AC3 cap, AC5 LLM failure + disk failure, AC6 invalid response (4 variants), AC7 timeout (8 variants), AC8 hostname, AC10 gate ordering.
- [x] All generated tests run successfully — `173 passed, 1 skipped`.
- [x] Tests use proper locators — substring assertions on stderr contract strings (`"Tailored package written to"`, `"Monthly LLM spend cap reached"`, `"LLM call failed:"`, `"--file"`, `"stdin"`, dollar amounts); file existence checks for `cv.md` / `cover-letter.md`; ledger schema checks on `total_usd` + `calls`.
- [x] Tests have clear descriptions — each docstring states the AC and the specific gap the test closes.
- [x] No hardcoded waits or sleeps — subprocess `timeout=5` is a failure guard only.
- [x] Tests are independent — `tmp_path` + `monkeypatch` rebuild state per test; isolated CLI env mirrors the canonical CV into the tmp tree; no shared mutable globals.
- [x] Test summary created — this file.
- [x] Tests saved to appropriate directories — `tests/unit/` and `tests/integration/`.
- [x] Summary includes coverage and gap-closure metrics.

## Files Modified

- `tests/unit/test_runtime_config.py` — +5 test names (+9 IDs with parametrize)
- `tests/unit/test_llm_client.py` — +3 test names
- `tests/integration/test_paste_tailoring.py` — +4 test names
- `tests/integration/test_paste_jd_ingest.py` — +1 test name

(No source-code changes. No `tests/conftest.py` fixture additions; the existing `tmp_canonical_cv` fixture and `_isolated_cli_env_with_fake_llm` helper pattern are sufficient.)

## Next Steps

- Tests are wired and green. No further action required for the Story 1.5 QA gate.
- Live LLM smoke (Task 11 sub-bullets in the story) remains the author's manual responsibility — it requires a real Anthropic API key and is deliberately out of `pytest` scope.
- When Epic 2 lands the structured per-application metadata sidecar (FR38) and `jobhunter stats` (FR40), the ledger schema in this story's tests will become the contract those future stories must extend without breaking.
