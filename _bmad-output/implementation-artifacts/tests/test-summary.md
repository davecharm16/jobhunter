# Test Automation Summary — Story 1.1

**Story:** Runtime, language, and canonical-CV schema bootstrap
**Generated:** 2026-05-23
**Author:** dave (via BMad qa-generate-e2e-tests)
**Framework chosen:** pytest 9.0.3 (added as `[project.optional-dependencies] dev` — Story 1.2 may formalize)
**Run command:** `.venv/bin/pytest -v` → **25 passed in 0.74s**

## Testing surface

Story 1.1 has **no HTTP API and no UI** — it is a CLI walking skeleton. The
testable surface is:

1. **Reader contract** (`jobhunter.canonical_cv.read_canonical_cv`) — FR4
2. **Config constants** (`jobhunter.config`) — AC #4 path is the single source of truth
3. **Committed sample** (`canonical-cv.json`) — AC #4, shape requirements from Task 3
4. **Validator script** (`scripts/validate_canonical_cv.py`) — AC #5 (subprocess / "API-like" CLI contract)
5. **CLI entry stub** (`jobhunter` console script + `python -m jobhunter.cli`) — AC #2

E2E in the CLI sense = subprocess invocation of the installed entry points
against an isolated workspace.

## Generated Tests

### Unit tests
- [x] `tests/unit/test_canonical_cv_reader.py` — 5 tests
  - happy-path parse, **FR4 no-cache re-read**, `CanonicalCVMissing` on missing file,
    subclass of `FileNotFoundError`, invalid-JSON surfacing
- [x] `tests/unit/test_config.py` — 7 tests
  - `CANONICAL_CV_PATH` type, repo-root anchoring, schema path location,
    committed sample + schema presence, module exports
- [x] `tests/unit/test_sample_cv.py` — 5 tests
  - basics+email present, ≥2 work entries with highlights, ≥3 skills with
    keywords, ≥1 project with highlights, ≥1 education entry

### Integration / CLI ("E2E") tests
- [x] `tests/integration/test_validate_script.py` — 5 tests
  - exit 0 on valid sample, exit 2 when CV missing, exit 2 when schema missing,
    exit 1 on invalid email format (FormatChecker), exit 1 on structural violation
  - Each test runs against an **isolated workspace** (copied script + schema +
    src/jobhunter + canonical-cv.json) so the committed files are never mutated
- [x] `tests/integration/test_cli_entry.py` — 3 tests
  - `jobhunter` console script → exit 2 with usage on stderr
  - `python -m jobhunter.cli` → exit 2 with usage
  - direct `main()` call → returns 2

### Shared fixtures
- `tests/conftest.py` — `tmp_canonical_cv`, `missing_canonical_cv`,
  `project_root`. Patches `CANONICAL_CV_PATH` in **both** `jobhunter.config`
  and `jobhunter.canonical_cv` because the reader binds the constant at
  import time.

## Coverage map (Story 1.1 acceptance criteria)

| AC | What it requires | Tests |
|----|------------------|-------|
| AC1 | DECISIONS.md exists & records runtime + rationale | not test-automatable (documentation gate) |
| AC2 | Runnable Python skeleton | covered by CLI entry tests (entry resolves & runs) |
| AC3 | `pip install -e .` exits 0 | enforced by test setup (pytest depends on installed package) |
| AC4 | Sample at configured path | `test_config::test_committed_canonical_cv_exists_at_configured_path` + sample shape tests |
| AC5 | Sample validates against vendored schema | `test_validate_script::test_validator_exits_zero_on_valid_sample` + 3 negative cases |
| AC6 | Schema choice + fallback in DECISIONS.md | not test-automatable (documentation gate) |
| AC7 | Single-path reader, no caching | `test_canonical_cv_reader::test_no_caching_fresh_read_each_call` + 4 others |

## Gaps auto-applied during this run

The story's "Testing standards" said no formal framework was required; this
workflow added one. Gaps discovered and applied:

1. **No FR4 regression test existed.** The story's Debug Log mentioned an
   inline smoke that proved fresh-read semantics; converted into a permanent
   pytest case (`test_no_caching_fresh_read_each_call`).
2. **Validator FormatChecker regression risk.** The story noted the email
   format check was easy to lose (initial implementation passed
   `not-an-email` until `FormatChecker()` was wired). Added a permanent
   negative test (`test_validator_exits_one_on_invalid_email`).
3. **Validator script was only smoke-tested.** Added structured exit-code
   coverage for the four documented branches (0 / 1 / 2 valid / 2 missing-schema).
4. **CV sample shape was unenforced.** Task 3 specified ≥ 2 work entries,
   ≥ 3 skills with keywords, ≥ 1 project, ≥ 1 education — now pinned by
   `test_sample_cv.py` so future edits cannot quietly thin out the fixture.
5. **CLI stub had no automated test.** Added subprocess + module + direct-call
   tests so Story 1.2's CLI rewrite can detect any unintended behavior drift.

## Next steps

- Story 1.2 may formalize pytest selection (already wired here as the de facto
  choice for the Python path).
- When Story 1.3 wires PDF/docx rejection, extend `test_canonical_cv_reader.py`
  with cases that ensure non-JSON canonical files raise the new rejection error.
- When Story 2.1 adds `tags` / `highImpact` extensions, extend `test_sample_cv.py`.
- Add a CI workflow that runs `pytest` on push (deferred until CI is in scope).

## Validation against `.claude/skills/bmad-qa-generate-e2e-tests/checklist.md`

- [x] API tests generated (if applicable) — N/A (no HTTP API); CLI/script contract covered instead
- [x] E2E tests generated (if UI exists) — N/A (no UI); subprocess CLI tests cover end-to-end
- [x] Tests use standard test framework APIs — pytest only
- [x] Tests cover happy path — yes (reader, validator, CLI)
- [x] Tests cover 1–2 critical error cases — yes (missing CV, missing schema, invalid email, structural violation, invalid JSON, missing-file exception)
- [x] All generated tests run successfully — 25/25 pass
- [x] Tests use proper locators — N/A for CLI; tests use exit codes + stderr substrings
- [x] Tests have clear descriptions — yes, docstring per file + descriptive names
- [x] No hardcoded waits or sleeps — none
- [x] Tests are independent (no order dependency) — yes; each integration test gets a fresh tmp workspace; unit tests use monkeypatched paths
- [x] Test summary created — this file
- [x] Tests saved to appropriate directories — `tests/unit/`, `tests/integration/`
- [x] Summary includes coverage metrics — yes (AC map above)
