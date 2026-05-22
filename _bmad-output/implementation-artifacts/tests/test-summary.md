# Test Automation Summary — Story 1.4

**Story:** `jobhunter paste` JD ingest from stdin or `--file` argument
**Date:** 2026-05-23
**Author:** dave (via BMad qa-generate-e2e-tests)
**Framework:** pytest 9.0.3 (existing project framework)
**Run command:** `.venv/bin/python -m pytest`
**Result:** **97 passed, 2 skipped in 1.69s**

Skips are pre-existing `python-dotenv` sandbox limitations from Story 1.2 (not introduced by this run). 15 new tests added; 0 regressions against the 82-test baseline.

## Testing Surface

Story 1.4 has no HTTP API and no UI. The automated surface is:

1. The `paste` subcommand's JD-ingest flow — stdin happy path, `--file` happy path, `--file` precedence over stdin, no-input rejections (TTY, empty pipe, whitespace), bad `--file` (missing, directory, etc.), and the env → CV → JD ordering invariant.
2. The boundary-message contract — exit code `1`, message references Story 1.5, character count, and source provenance (`stdin` or `--file PATH`).
3. The static guardrails — no new runtime dependency, no LLM/HTTP/job-board client imports, no `./out/` write in Story 1.4.

## Gap Analysis (test additions in this run)

The Story 1.4 dev pass landed 11 new tests covering AC1–AC10 at a high level. The QA pass identified 7 gaps in contract strictness and unattended invariants, and closed each with 15 new tests in a dedicated module:

| # | Gap | New test(s) |
|---|---|---|
| 1 | AC11 stdlib-only guardrail at source level — no test prevented an accidental `import requests`/`httpx`/`openai`/`anthropic`/`click`/`typer`/`rich` in `cli.py` | `test_cli_module_does_not_import_forbidden_runtime_deps` |
| 2 | AC11 `pyproject.toml` deps pin — no test prevented a future dev from adding a runtime dependency | `test_pyproject_runtime_dependencies_did_not_grow_in_story_1_4` |
| 3 | UTF-8 encoding contract for `--file` — `Path.read_text(encoding="utf-8")` claim untested against non-ASCII content | `test_paste_subprocess_file_with_utf8_unicode_content_succeeds`, `test_cli_paste_in_process_utf8_file_char_count_reflects_unicode_length` |
| 4 | AC5-symmetric: empty / whitespace-only `--file` content was not tested (only empty/whitespace stdin) | `test_paste_subprocess_empty_file_exits_two`, `test_paste_subprocess_whitespace_only_file_exits_two`, `test_cli_paste_in_process_empty_file_exits_two` |
| 5 | AC8 ordering for the `--file` branch — env-failure tests all piped stdin; no test proved a provided `--file` is *not* opened before `LLM_API_KEY`/`MONTHLY_SPEND_CAP_USD` are validated | `test_paste_subprocess_missing_llm_key_does_not_read_provided_file` (uses a sentinel string the file content must NOT leak into stderr), `test_paste_subprocess_missing_cap_does_not_read_provided_file` |
| 6 | AC9 strict boundary-message shape — existing tests checked only that the literal `"--file"` substring appears, not the verbatim path nor the `{n} chars` count | `test_paste_subprocess_boundary_message_includes_char_count_and_file_path`, `test_paste_subprocess_boundary_message_for_stdin_includes_char_count` |
| 7 | AC10 success path: existing tests asserted no `./out/` on rejection paths and one in-process file test, but no **subprocess** test pinned the success-path side-effect contract for either `--file` or stdin | `test_paste_subprocess_success_does_not_create_out_directory_with_file`, `test_paste_subprocess_success_does_not_create_out_directory_with_stdin` |
| 8 | `--file=PATH` (equals syntax) — `argparse` supports it natively, but no smoke test confirmed it survives the dispatch chain | `test_paste_subprocess_file_equals_syntax_works` |
| 9 | AC3 in-process companion — only a subprocess test covered `--file` precedence over a piped stdin; in-process coverage was missing | `test_cli_paste_in_process_file_precedence_over_stdin` |

## Generated Tests

### CLI Integration Tests — `tests/integration/test_paste_jd_ingest.py` (+15, new file)

Subprocess tests (12):

- `test_cli_module_does_not_import_forbidden_runtime_deps` — AC11 forbidden-import source check
- `test_pyproject_runtime_dependencies_did_not_grow_in_story_1_4` — AC11 deps-list pin
- `test_paste_subprocess_file_with_utf8_unicode_content_succeeds` — UTF-8 round-trip via `--file`
- `test_paste_subprocess_empty_file_exits_two` — AC5-symmetric: empty `--file`
- `test_paste_subprocess_whitespace_only_file_exits_two` — AC5-symmetric: whitespace `--file`
- `test_paste_subprocess_missing_llm_key_does_not_read_provided_file` — AC8 ordering, file branch
- `test_paste_subprocess_missing_cap_does_not_read_provided_file` — AC8 ordering, file branch
- `test_paste_subprocess_boundary_message_includes_char_count_and_file_path` — AC9 strict shape (file)
- `test_paste_subprocess_boundary_message_for_stdin_includes_char_count` — AC9 strict shape (stdin)
- `test_paste_subprocess_success_does_not_create_out_directory_with_file` — AC10 success path (file)
- `test_paste_subprocess_success_does_not_create_out_directory_with_stdin` — AC10 success path (stdin)
- `test_paste_subprocess_file_equals_syntax_works` — argparse `--file=PATH` smoke test

In-process tests (3):

- `test_cli_paste_in_process_utf8_file_char_count_reflects_unicode_length` — UTF-8 + char-count contract
- `test_cli_paste_in_process_empty_file_exits_two` — AC5-symmetric: in-process variant
- `test_cli_paste_in_process_file_precedence_over_stdin` — AC3 in-process companion

The new file mirrors `_isolated_cli_env(tmp_path, ...)`, `_pythonpath_with_src`, `_cli_env`, and `_run_module_cli` locally (kept private to the test module) so the gap-closure suite is self-contained and `tests/integration/test_cli_entry.py` does not have to grow past its current ~845 lines.

### No Source-Code Changes

No `src/jobhunter/cli.py` change is needed — the Story 1.4 dev pass already implements the contract correctly. The QA tests are pure gap-closure: they validate the already-implemented behavior and prevent future regressions.

## Coverage

- **JD-ingest contract:** 26/26 known behaviors (AC1–AC10 + AC11 source guardrails). The 11 Story-1.4 dev tests + 15 QA gap-closure tests cover stdin/`--file` happy paths, `--file` precedence, empty/whitespace rejections in both branches, missing-file, directory `--file`, TTY-no-input rejection, env → CV → JD ordering invariants for both stdin and `--file` branches, boundary-message strict shape (char count + source path), UTF-8 encoding for `--file`, `--file=PATH` equals syntax, success-path no-`./out/` side effect.
- **AC11 guardrails:** Forbidden imports in `cli.py` and forbidden runtime deps in `pyproject.toml` are now both load-bearing assertions.
- **No new runtime dependency added:** All new tests use stdlib + pytest only (`subprocess`, `pathlib`, `io`, `os`, `shutil`, `sys`).
- **Full pytest suite:** 97/97 passing (+ 2 pre-existing dotenv-sandbox skips). Baseline before this run: 82/82 passing.

## Validation Against `checklist.md`

- [x] API tests generated (if applicable) — N/A; no HTTP service exists yet (lands in Story 2.11).
- [x] E2E tests generated (if UI exists) — N/A for UI; CLI subprocess + in-process integration tests cover the user-facing surface.
- [x] Tests use standard test framework APIs — pytest + `monkeypatch` + `capsys`, stdlib `subprocess` and `io`. No custom abstractions.
- [x] Tests cover happy path — UTF-8 `--file` happy path, stdin happy path with char-count assertions, `--file=PATH` equals syntax, in-process precedence.
- [x] Tests cover critical error cases — empty `--file`, whitespace `--file`, env-missing with `--file` present (no file read), boundary-message strict shape on success.
- [x] All generated tests run successfully (`97 passed, 2 skipped`).
- [x] Tests use proper locators — substring assertions on `"Story 1.5"`, `"--file"`, `"stdin"`, char-count strings, and path strings (copywriting-stable per Story 1.4 Dev Notes Testing Standards).
- [x] Tests have clear descriptions — each docstring states the AC and the specific gap the test closes.
- [x] No hardcoded waits or sleeps — subprocess `timeout=5` is a failure guard only.
- [x] Tests are independent — `tmp_path` + `monkeypatch` rebuild state per test; the `_isolated_cli_env` helper builds the env in tmp_path before snapshotting; no shared mutable globals.
- [x] Test summary created — this file.
- [x] Tests saved to appropriate directories — `tests/integration/test_paste_jd_ingest.py` (new file).
- [x] Summary includes coverage and gap-closure metrics.

## Files Modified

- `tests/integration/test_paste_jd_ingest.py` — new file, 15 tests, ~440 lines.

(No source code changes. No `tests/conftest.py` fixture additions; the existing `tmp_canonical_cv` fixture and `_isolated_cli_env(tmp_path, ...)` helper pattern are sufficient.)

## Next Steps

- No source changes needed for Story 1.4; gap-closure tests validate the already-implemented behavior.
- When Story 1.5 lands the first tailoring call, extend this suite to confirm: (a) the JD text reaches the tailoring step exactly once (no double-read), (b) the boundary message changes from "Story 1.5" to whatever the next-boundary message is, and (c) the first `./out/<slug>/` write now appears — the AC10 success-path assertions in this file will need to be updated or moved to Story 1.5's QA pass.
- The two new AC11 static guardrails (`test_cli_module_does_not_import_forbidden_runtime_deps`, `test_pyproject_runtime_dependencies_did_not_grow_in_story_1_4`) should be extended in Story 1.5 to allow the chosen LLM SDK (e.g. `anthropic` or `openai`) while still blocking the others.
