# Story 1.3: Canonical CV reader with PDF/docx ingest rejection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a solo developer (the author),
I want the pipeline to read the canonical CV fresh from a text file on every run and explicitly reject any PDF or docx ingest attempt,
so that I never re-import my CV, I get diffable/mergeable history for free, and the "no binary canonical CV" stance is enforced in code rather than documentation (FR1, FR4, FR5).

## Acceptance Criteria

1. **AC1 — Reader returns parsed CV on every call (no caching).** With a readable canonical CV at `CANONICAL_CV_PATH`, `read_canonical_cv()` returns the parsed in-memory dictionary, and every invocation re-reads from disk so a mutation between calls is visible on the next call (FR1, FR4). The single reader contract from Story 1.1 stays the only code path that loads the canonical CV.

2. **AC2 — `.pdf` path is rejected before any JSON parse or LLM call.** When `CANONICAL_CV_PATH` points to a `.pdf` file (any case: `.pdf`, `.PDF`), the reader raises a typed exception whose message contains the literal substring `"PDF"` and states that the canonical CV must be a text format (JSON, markdown, or YAML), and the CLI surfaces this with a non-zero exit code. No LLM call, no HTTP call, no `./out/` write occurs (FR5, FR44).

3. **AC3 — `.docx` / `.doc` path is rejected before any JSON parse or LLM call.** When `CANONICAL_CV_PATH` points to `.docx` / `.DOCX` / `.doc` / `.DOC`, the reader raises a typed exception whose message contains the literal substring `"docx"` and also references Word, states that the canonical CV must be a text format (JSON, markdown, or YAML), and the CLI surfaces this with a non-zero exit code. No LLM call, no HTTP call, no `./out/` write occurs (FR5, FR44).

4. **AC4 — Missing file is rejected with the path in the message.** When `CANONICAL_CV_PATH` points to a path that does not exist, the reader raises `CanonicalCVMissing` (the existing Story 1.1 exception type) whose message contains the missing file path verbatim, and the CLI surfaces this with a non-zero exit code. No LLM call, no HTTP call, no `./out/` write occurs.

5. **AC5 — Reader exposes a typed unsupported-format exception.** A new exception type, named `UnsupportedCanonicalCVFormat`, lives in `src/jobhunter/canonical_cv.py` alongside `CanonicalCVMissing`. It is the single exception raised for binary-format rejection (`.pdf`, `.docx`, `.doc`) so callers can map it to one CLI exit path without inspecting message strings. Both exceptions are exported from the module's public surface (re-bind in `__all__` or expose by import in `__init__.py` if a public surface is established).

6. **AC6 — `jobhunter paste` invokes the reader after env validation and exits cleanly on every reader failure.** The existing `handle_paste()` flow becomes: (1) load runtime config, (2) call `read_canonical_cv()`, (3) only on success print the existing "Story 1.4" scaffold message and return non-zero. On `ConfigurationError`, `UnsupportedCanonicalCVFormat`, or `CanonicalCVMissing`, the CLI prints the exception message to stderr and returns a non-zero exit code; the success path's "Story 1.4" message must not appear when a reader error fires.

7. **AC7 — Rejection path strictly prevents any LLM, HTTP, or artifact-write side effect.** The implementation must not import an LLM SDK, must not import `requests` / `httpx`, must not create `./out/`, and must not consume stdin or read a `--file` argument during a rejection path. AC8/AC9 of Story 1.2 stay enforced; Story 1.3 inherits the "no job-board submit code anywhere" guardrail.

8. **AC8 — Tests cover the reader contract and the CLI rejection path.** Pytest suite additions:
   - Unit tests in `tests/unit/test_canonical_cv_reader.py` cover `.pdf`, `.PDF`, `.docx`, `.DOCX`, `.doc` rejection paths and assert that the error message contains the case-correct substring (`"PDF"` for `.pdf` / `.PDF`; `"docx"` and a `"Word"` reference for `.docx` / `.doc`).
   - Existing happy-path and missing-file tests stay green.
   - Integration tests in `tests/integration/test_cli_entry.py` cover `jobhunter paste` with valid env plus a `.pdf` / `.docx` / missing `CANONICAL_CV_PATH`, asserting non-zero exit code, the required substrings in stderr, and that the "Story 1.4" message is NOT printed.

9. **AC9 — No new runtime dependency is added.** The implementation must rely only on stdlib plus the libraries already pinned in `pyproject.toml` (`jsonschema`, `python-dotenv`, `pytest`). Do not add `python-docx`, `pdfminer`, or anything that would imply we actually parse those formats — the rejection must be path-extension-only, before any read attempt.

10. **AC10 — Reader does not perform JSON Resume schema validation.** Schema validation lives in `scripts/validate_canonical_cv.py` (Story 1.1) and is not duplicated in the runtime reader. The reader still raises naturally on malformed JSON via `json.JSONDecodeError` (verified by the existing Story 1.1 test). Adding schema enforcement inside `read_canonical_cv()` is out of scope for Story 1.3.

## Tasks / Subtasks

- [x] **Task 1: Add `UnsupportedCanonicalCVFormat` and binary-format rejection in the reader** (AC: #2, #3, #5)
  - [x] Edit `src/jobhunter/canonical_cv.py` and add `class UnsupportedCanonicalCVFormat(ValueError)` (use `ValueError` as the base; the misuse-of-file-format condition is a value error, not a `FileNotFoundError` subclass).
  - [x] Build a small private constant such as `_REJECTED_SUFFIXES = {".pdf", ".docx", ".doc"}`.
  - [x] In `read_canonical_cv()`, before the `open()`, compute `suffix = CANONICAL_CV_PATH.suffix.lower()` and branch on rejected suffixes before doing anything else.
  - [x] For `.pdf`: raise `UnsupportedCanonicalCVFormat` with a message containing the literal substring `"PDF"` and stating "the canonical CV must be JSON, markdown, or YAML (not PDF)". Include the configured path so the user can see what was misconfigured.
  - [x] For `.docx` / `.doc`: raise `UnsupportedCanonicalCVFormat` with a message containing both the literal substring `"docx"` and a reference to `"Word"`, stating "the canonical CV must be JSON, markdown, or YAML (not Word/docx)". Include the configured path.
  - [x] Do not call `open()`, do not call `json.load()`, do not log to disk, do not import or trigger anything LLM/HTTP-related on the rejection path.

- [x] **Task 2: Confirm `CanonicalCVMissing` message includes the missing path** (AC: #4)
  - [x] Verify the existing `CanonicalCVMissing` message already includes `CANONICAL_CV_PATH`; if not, adjust it so the missing path appears verbatim in the exception text.
  - [x] Keep `CanonicalCVMissing` as a subclass of `FileNotFoundError` (Story 1.1 contract) so external code can still catch the broader category if it wants.

- [x] **Task 3: Wire the reader into `handle_paste()` and translate reader failures to clean CLI exit codes** (AC: #6, #7)
  - [x] Edit `src/jobhunter/cli.py`. After the `load_runtime_config()` call succeeds, call `read_canonical_cv()` inside a `try` block.
  - [x] Catch `UnsupportedCanonicalCVFormat` and `CanonicalCVMissing` (the latter via its concrete class, not the broad `FileNotFoundError`). On either, print `f"Canonical CV error: {exc}"` to stderr and return a non-zero exit code (use `2` to match the existing config-error convention).
  - [x] Only when the reader succeeds, print the existing "jobhunter paste is scaffolded; JD ingest lands in Story 1.4." message and return `1` (preserves the Story 1.2 behavior so the test `test_cli_paste_reaches_story_1_4_boundary_with_valid_env` still passes when `CANONICAL_CV_PATH` resolves to a valid file).
  - [x] Do NOT import any LLM SDK, `requests`, `httpx`, or job-board client.
  - [x] Do NOT read stdin or accept `--file` (still Story 1.4 scope).

- [x] **Task 4: Extend `conftest.py` fixtures for `.pdf` / `.docx` / `.doc` paths** (AC: #2, #3)
  - [x] In `tests/conftest.py`, add fixtures that monkeypatch `CANONICAL_CV_PATH` to point at a `tmp_path / "canonical-cv.pdf"`, `tmp_path / "canonical-cv.docx"`, and `tmp_path / "canonical-cv.doc"` (and uppercase variants where you want them).
  - [x] The fixtures must create empty (zero-byte) files at those paths so the test confirms rejection happens by extension **before** any read attempt — if the implementation incorrectly tries to JSON-parse them, an empty file would raise `json.JSONDecodeError`, not `UnsupportedCanonicalCVFormat`, and the test would fail loudly.
  - [x] Patch the constant in both `jobhunter.config` and `jobhunter.canonical_cv` like the existing `tmp_canonical_cv` fixture (the existing comment in `conftest.py` explains why both bindings must be patched).

- [x] **Task 5: Add reader unit tests for rejection** (AC: #2, #3, #5, #8)
  - [x] Add tests in `tests/unit/test_canonical_cv_reader.py`:
    - `.pdf` path → `pytest.raises(UnsupportedCanonicalCVFormat)`; assert `"PDF"` in `str(exc.value)`; assert `CANONICAL_CV_PATH` value appears in the message.
    - `.PDF` (uppercase) → same expectation, confirming case-insensitivity.
    - `.docx` path → `pytest.raises(UnsupportedCanonicalCVFormat)`; assert both `"docx"` and `"Word"` substrings appear in the message.
    - `.DOCX` (uppercase) → same.
    - `.doc` path → `pytest.raises(UnsupportedCanonicalCVFormat)`; same substring assertions.
    - `UnsupportedCanonicalCVFormat` subclasses `ValueError` (so callers can catch the broader category if needed).
  - [x] Keep all four existing tests in this file passing without modification.

- [x] **Task 6: Add CLI integration tests for the rejection path** (AC: #6, #7, #8)
  - [x] In `tests/integration/test_cli_entry.py`, add subprocess-level tests that:
    - Run `jobhunter paste` (or `python -m jobhunter.cli paste`) with valid `LLM_API_KEY` + `MONTHLY_SPEND_CAP_USD` env and a temporary copy of `src/` whose `CANONICAL_CV_PATH` points at a `.pdf` file (use the existing `_isolated_cli_env` helper as a model — you may need a variant that lets the test write a `canonical-cv.pdf` and patches `CANONICAL_CV_PATH` via env or a tiny patch script). If subprocess patching is too invasive, drop to an in-process `main([...])` test using `monkeypatch.setattr` on the constant — both paths are acceptable.
    - Assert exit code is non-zero (use `>= 1`, not exactly `1`, so Task 3's `return 2` is acceptable).
    - Assert `"PDF"` appears in stderr (for the `.pdf` test) and `"docx"` + `"Word"` appear in stderr (for the `.docx` test).
    - Assert `"Story 1.4"` does NOT appear in stderr.
    - Assert no `./out/` directory exists in the test cwd after the run.
  - [x] Add at least one in-process unit-style test (`from jobhunter.cli import main`) for each rejection path so coverage does not depend on subprocess support.

- [x] **Task 7: Document the rejection contract in `DECISIONS.md` and `README.md`** (AC: #2, #3)
  - [x] Append a short subsection to `DECISIONS.md` §2 (or add §4 "Canonical CV format rejection") stating that the runtime reader rejects `.pdf`, `.docx`, and `.doc` extensions before any read attempt, and that this is enforcement of FR5.
  - [x] Add one or two lines to `README.md` Configuration section noting that the canonical CV must be a text format (JSON committed today; markdown/YAML allowed if the schema fallback fires per Story 2.1) and PDF/docx are explicitly unsupported.

- [x] **Task 8: Verification** (AC: #1–#10)
  - [x] Run `pip install -e ".[dev]"`. (skipped — sandbox venv has no PyPI access; matches Story 1.2's documented workaround. Editable install is pre-existing in `.venv/`.)
  - [x] Run `python scripts/validate_canonical_cv.py` — must still exit 0. (exit=0)
  - [x] Run `jobhunter` (no args) — must still exit `2`. (exit=2)
  - [x] Run `jobhunter --help` — must still exit `0` with the no-auto-submit statement intact. (exit=0; statement intact)
  - [x] Run `jobhunter paste` with no env — must still exit non-zero naming `LLM_API_KEY`. (exit=2; `LLM_API_KEY is required...`)
  - [x] Run `LLM_API_KEY=test-key MONTHLY_SPEND_CAP_USD=25.00 jobhunter paste` against the committed `canonical-cv.json` — must reach the "Story 1.4" boundary as before. (exit=1; "jobhunter paste is scaffolded; JD ingest lands in Story 1.4.")
  - [x] Run `pytest`. All previous tests pass; all new tests pass. (58 passed, 2 dotenv-sandbox skips — pre-existing per Story 1.2.)

## Dev Notes

### Current state of the canonical-CV reader (what Story 1.3 modifies)

- `src/jobhunter/canonical_cv.py` already exposes `read_canonical_cv()` and `CanonicalCVMissing`, but its module docstring explicitly says: *"PDF/docx rejection logic is intentionally NOT implemented here; that lands in Story 1.3."* Story 1.3 is the story that lands it. [Source: src/jobhunter/canonical_cv.py#L8-L10]
- `CANONICAL_CV_PATH` is a single constant in `src/jobhunter/config.py` pointing at `canonical-cv.json`. No other code in the repo hard-codes the path; the reader is the single entry point per the Story 1.1 contract. [Source: src/jobhunter/config.py#L10-L12; DECISIONS.md#2-canonical-cv-schema]
- `CanonicalCVMissing` already subclasses `FileNotFoundError`, and its existing message already includes the path: `"Canonical CV not found at {CANONICAL_CV_PATH}"`. AC4 expects that to continue. [Source: src/jobhunter/canonical_cv.py#L18-L38]
- The existing `tmp_canonical_cv` and `missing_canonical_cv` fixtures already monkeypatch `CANONICAL_CV_PATH` in *both* `jobhunter.config` and `jobhunter.canonical_cv` because the reader rebinds the constant at import time. New `.pdf` / `.docx` fixtures must follow the same pattern. [Source: tests/conftest.py#L46-L74]
- `handle_paste()` currently has exactly two states: env-invalid → exit 2; env-valid → print the Story 1.4 message and exit 1. Story 1.3 inserts the reader call between those two states. [Source: src/jobhunter/cli.py#L37-L48]

### Discrepancy between the epic AC wording and the committed schema (resolved)

The Story 1.3 epic AC says the error message should state that the canonical CV must be "markdown or YAML" (drawn from PRD FR1/FR5 which talk about a markdown/YAML source-of-truth). However, Story 1.1 committed JSON Resume v1.0.0 as the working assumption and `canonical-cv.json` (JSON) is the only format actually committed in the repo today. To honor both: the reader's error message must include the literal substrings the ACs above require (`"PDF"`, `"docx"`, `"Word"`) AND state that the canonical CV must be a text format — JSON, markdown, or YAML — so the message stays truthful to what's committed (`canonical-cv.json` is JSON) without contradicting the original PRD intent. Do NOT change the canonical schema, do NOT add markdown/YAML parsing in Story 1.3 — that is out of scope and is gated by the explicit JSON Resume fall-back criterion in `DECISIONS.md` §2. [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3 ACs; DECISIONS.md#2-canonical-cv-schema]

### Architecture and product constraints (unchanged from Stories 1.1 and 1.2)

- There is no separate Architecture or UX document. The PRD plus the epics file are the source of truth. [Source: _bmad-output/planning-artifacts/epics.md#L15-L21]
- Epic 1 is the walking skeleton. Keep scope tight: harden the reader and route exceptions through the CLI. No drift checks, no LLM calls, no `./out/<slug>/` writes, no JD ingest. [Source: _bmad-output/planning-artifacts/epics.md#L263-L265]
- Local-first runtime; filesystem-only persistence. No database. [Source: _bmad-output/planning-artifacts/prd.md#L353-L359]
- Cost-cap and no-auto-submit guardrails inherited from Story 1.2 must remain unbroken. The reader work in Story 1.3 must not regress AC5, AC6, or AC9 of Story 1.2. [Source: _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md]

### Recommended implementation shape

Keep the diff small and surgical. The dataflow after Story 1.3 should read:

```text
jobhunter paste
  → load_runtime_config()           (Story 1.2)
  → read_canonical_cv()              (Story 1.3 — new)
  → print "Story 1.4 boundary"       (Story 1.2 — preserved)
```

Reader shape after Story 1.3:

```python
class CanonicalCVMissing(FileNotFoundError):
    ...

class UnsupportedCanonicalCVFormat(ValueError):
    """Raised when CANONICAL_CV_PATH points to a binary (PDF/docx) format."""


_REJECTED_SUFFIXES = {".pdf", ".docx", ".doc"}


def read_canonical_cv() -> dict[str, Any]:
    suffix = CANONICAL_CV_PATH.suffix.lower()
    if suffix == ".pdf":
        raise UnsupportedCanonicalCVFormat(
            f"PDF canonical CV at {CANONICAL_CV_PATH} is not supported; "
            "the canonical CV must be a text format (JSON, markdown, or YAML)."
        )
    if suffix in {".docx", ".doc"}:
        raise UnsupportedCanonicalCVFormat(
            f"Word/docx canonical CV at {CANONICAL_CV_PATH} is not supported; "
            "the canonical CV must be a text format (JSON, markdown, or YAML)."
        )

    try:
        with open(CANONICAL_CV_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise CanonicalCVMissing(
            f"Canonical CV not found at {CANONICAL_CV_PATH}"
        ) from exc
```

CLI integration:

```python
def handle_paste() -> int:
    try:
        load_runtime_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        read_canonical_cv()
    except UnsupportedCanonicalCVFormat as exc:
        print(f"Canonical CV error: {exc}", file=sys.stderr)
        return 2
    except CanonicalCVMissing as exc:
        print(f"Canonical CV error: {exc}", file=sys.stderr)
        return 2

    print(
        "jobhunter paste is scaffolded; JD ingest lands in Story 1.4.",
        file=sys.stderr,
    )
    return 1
```

The return value `1` for the "Story 1.4 boundary" success path must stay `1` exactly, so `test_cli_paste_reaches_story_1_4_boundary_with_valid_env` and `test_paste_subprocess_valid_env_stops_at_story_1_4_boundary` keep passing.

### Library / framework requirements

- Stdlib only for the rejection logic: `pathlib.Path.suffix.lower()` is enough. No regex, no MIME-sniffing, no `magic`. The decision is path-extension-based by design — the reader's job is to never even open a binary file (so we can't be tricked into reading megabytes off disk before raising).
- No new runtime dependency. `python-docx`, `pdfminer`, `pypdf`, etc. are explicitly disallowed because parsing the binary formats is the opposite of what FR5 asks for.
- Pytest stays the test framework (Story 1.1 + 1.2 contract).

### Previous-story intelligence (from Story 1.2)

- The dev agent that closed Story 1.2 ran tests in a sandboxed venv where DNS to PyPI was blocked, so `pip install` had to be skipped during code review. The existing `python-dotenv` import in `runtime_config.py` already handles the "dotenv not installed" case gracefully — keep that pattern intact. [Source: _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md#L256-L262]
- Story 1.2's review caught a `MEDIUM` finding because the original CLI subprocess tests could be polluted by a developer's real `.env` at `PROJECT_ROOT`. The fix was to copy `src/jobhunter` into a temporary directory and run the subprocess against the copy. The same `_isolated_cli_env` helper in `tests/integration/test_cli_entry.py` is the right pattern for any new subprocess tests Story 1.3 adds, because Story 1.3's tests must override `CANONICAL_CV_PATH` and the existing constant resolves from `__file__` — copying `src/jobhunter` into a tmp tree and editing the copied `config.py` (or, simpler, patching via env var in an in-process test) avoids the same class of bug. [Source: _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md#L256-L262]
- The Story 1.2 dev agent skipped two dotenv-related tests because the sandbox venv had no `python-dotenv`. Story 1.3 must not regress that — do not add new tests that require a `pip install` to pass; if a new test would need an unusual dependency, fixture it instead.

### Git intelligence

- Two prior commits on `main`: `feat(story-1.1): Runtime, language, and canonical-CV schema bootstrap` and `feat(story-1.2): CLI scaffold, .env secrets handling, and cost-cap config`. Story 1.3's commit message convention should match: `feat(story-1.3): canonical-cv reader with PDF/docx ingest rejection`.
- The `_bmad-output/story-automator/orchestration-1-...` file is currently dirty in the working tree but is owned by the BMAD automator and is not part of Story 1.3's implementation surface. Do not stage or modify it.

### Scope guardrails (what Story 1.3 must NOT do)

- ❌ Do not implement `--file` JD ingest. That is **Story 1.4**.
- ❌ Do not implement stdin JD reading. That is **Story 1.4**.
- ❌ Do not call any LLM API. The first LLM call is **Story 1.5**.
- ❌ Do not implement actual markdown or YAML parsing of the canonical CV. The canonical schema today is JSON Resume v1.0.0; adding new format parsers requires `DECISIONS.md` §2's fall-back criterion to fire, which is owned by **Story 2.1**.
- ❌ Do not add `tags` or `highImpact` extensions to the canonical CV. That is **Story 2.1**.
- ❌ Do not migrate tunables to `config.yaml`. That is **Story 2.2**.
- ❌ Do not add `python-docx`, `pdfminer`, `pypdf`, MIME detection, or any binary-format-aware library. The rejection must be path-extension-only and must happen before `open()`.
- ❌ Do not add HTTP clients, browser automation, or job-board SDKs. The Story 1.2 AC9 "no submit code" guardrail is still in force.
- ❌ Do not introduce per-request cost logging or a cost ledger. That is **Story 2.10**.
- ❌ Do not change the canonical CV file's location or rename `canonical-cv.json`. `CANONICAL_CV_PATH` is the single source of truth.
- ❌ Do not add JSON-Schema validation to the runtime reader. That is the validator script's job (Story 1.1) and the reader stays a thin loader.

### Project Structure Notes

- All new code lands under `src/jobhunter/` and `tests/`. No new top-level files except the `DECISIONS.md` and `README.md` edits in Task 7.
- Do not move `_bmad/`, `_bmad-output/`, `schemas/`, `scripts/`, or `canonical-cv.json`.
- The conftest fixtures pattern (patching `CANONICAL_CV_PATH` in both `jobhunter.config` and `jobhunter.canonical_cv`) is mandatory for any new fixture because the reader does `from jobhunter.config import CANONICAL_CV_PATH` at import time. Skipping the second `monkeypatch.setattr` is the most common test-isolation footgun in this repo.

### Testing Standards

- Continue Story 1.1 + 1.2 conventions:
  - `tests/unit/` for module-level behavior (reader logic, exception shapes).
  - `tests/integration/` for CLI subprocess + in-process behavior.
- Use the existing `tmp_canonical_cv` / `missing_canonical_cv` fixtures as the template for new `.pdf` / `.docx` / `.doc` fixtures.
- Subprocess tests in `tests/integration/test_cli_entry.py` must use `_isolated_cli_env` (or an equivalent isolated copy) so the developer's local `canonical-cv.json` cannot bleed in.
- Assertions on stderr should anchor on the substrings the ACs require (`"PDF"`, `"docx"`, `"Word"`, and the configured path) rather than full-message equality — copywriting can change, contract substrings cannot.
- Coverage focus is the safety contract, not aesthetics. At minimum prove:
  - `.pdf` and `.docx` and `.doc` rejection paths each raise `UnsupportedCanonicalCVFormat` with the required substrings.
  - Case-insensitive rejection works (`.PDF`, `.DOCX`).
  - Missing-file rejection still raises `CanonicalCVMissing` with the path.
  - Reader still re-reads on every call (FR4 regression guard from Story 1.1 stays green).
  - `jobhunter paste` in CLI form prints the rejection message to stderr, returns non-zero, and does not print the "Story 1.4 boundary" message.
  - `jobhunter paste` with a valid `canonical-cv.json` still hits the Story 1.4 boundary (regression guard for Story 1.2 AC8).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#L324-L351] — Story 1.3 requirements, BDD acceptance criteria.
- [Source: _bmad-output/planning-artifacts/epics.md#L237] — FR coverage for Epic 1 (FR1, FR4, FR5 land here).
- [Source: _bmad-output/planning-artifacts/epics.md#L29-L33] — FR1, FR4, FR5 text.
- [Source: _bmad-output/planning-artifacts/prd.md#L353-L362] — local-first runtime, filesystem-only persistence.
- [Source: _bmad-output/implementation-artifacts/1-1-runtime-language-and-canonical-cv-schema-bootstrap.md] — Story 1.1: reader contract stub, `CanonicalCVMissing`, conftest fixture pattern.
- [Source: _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md] — Story 1.2: `handle_paste` shape, `_isolated_cli_env` subprocess pattern, dotenv-sandbox skip handling.
- [Source: DECISIONS.md#2-canonical-cv-schema] — JSON Resume v1.0.0 committed; markdown/YAML fall-back gated by Story 2.1.
- [Source: src/jobhunter/canonical_cv.py#L8-L38] — current reader stub that Story 1.3 hardens.
- [Source: src/jobhunter/cli.py#L37-L48] — `handle_paste()` shape to extend.
- [Source: src/jobhunter/config.py#L10-L12] — `CANONICAL_CV_PATH` constant.
- [Source: tests/conftest.py#L45-L74] — fixture pattern for patching `CANONICAL_CV_PATH` in both modules.
- [Source: tests/unit/test_canonical_cv_reader.py] — existing reader contract tests to keep green.
- [Source: tests/integration/test_cli_entry.py#L37-L46] — `_isolated_cli_env` helper for subprocess isolation.
- [Source: pyproject.toml] — current pinned deps; no additions in Story 1.3.

## Create-Story Validation Notes

- Re-analyzed the epics file (Story 1.3 ACs and Epic 1 FR coverage), PRD FR1/FR4/FR5 wording, Stories 1.1 and 1.2 implementation artifacts, current `src/jobhunter/` source, `tests/` layout and fixture pattern, sprint status, and the last two commits on `main`.
- No Architecture or UX artifact exists; the PRD + epics file are the technical source of truth (consistent with Stories 1.1 and 1.2).
- Disaster-prevention guardrails enumerated for the dev agent: do not parse binary formats (rejection is by extension, before `open()`); do not add LLM, HTTP, or job-board code; do not start JD ingest (Story 1.4) or markdown/YAML parsing (gated by Story 2.1's fall-back criterion); preserve the `_isolated_cli_env` subprocess pattern so a developer's real `canonical-cv.json` cannot pollute test runs.
- Discrepancy between the epic AC wording ("must be markdown or YAML") and the committed schema (JSON Resume v1.0.0) is called out explicitly with a concrete resolution: the error message must include the AC-required substrings AND a truthful "JSON, markdown, or YAML" phrasing. The dev agent will not have to make this judgment call on the fly.
- The reader interface stays a no-argument function; testability is preserved via the existing conftest fixture pattern (`monkeypatch` of `CANONICAL_CV_PATH` in both `jobhunter.config` and `jobhunter.canonical_cv`).

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (Opus 4.7, 1M context)

### Debug Log References

- Initial red-phase reader unit tests (`tests/unit/test_canonical_cv_reader.py`) failed with `ImportError: cannot import name 'UnsupportedCanonicalCVFormat'`, confirming the new symbol was the only missing piece before green-phase implementation in `src/jobhunter/canonical_cv.py`.
- Initial red-phase CLI integration tests printed the Story 1.4 boundary message regardless of CV format, confirming `handle_paste()` had not yet been wired to the reader (the gap Task 3 closes).
- After wiring the reader into `handle_paste()`, the pre-existing `test_paste_subprocess_valid_env_stops_at_story_1_4_boundary` regressed because `_isolated_cli_env` copied `src/jobhunter` into `tmp_path/src/` but did not mirror `canonical-cv.json` into `tmp_path/`. Resolved by extending `_isolated_cli_env` to also copy the committed `canonical-cv.json` into the isolated tree; this keeps the isolation pattern from Story 1.2 intact while making it Story-1.3-aware.
- Story 1.2's documented dotenv-sandbox limitation continues to apply: two `test_runtime_config.py` tests skip when `python-dotenv` is unavailable in the sandbox venv. No new tests were added that require a `pip install` to pass.

### Completion Notes List

- `read_canonical_cv()` now rejects `.pdf`, `.docx`, and `.doc` (case-insensitive) by extension **before** any `open()` or `json.load()`, satisfying FR5 with zero new runtime dependencies. Rejection raises `UnsupportedCanonicalCVFormat(ValueError)`, which is exported from `jobhunter.canonical_cv` alongside `CanonicalCVMissing` via `__all__`.
- The reader's error messages carry the AC-required substrings — `"PDF"` for PDF rejection; `"docx"` + `"Word"` for docx/doc rejection — together with a truthful "JSON, markdown, or YAML" phrasing that honors the Dev Notes' discrepancy resolution between the PRD wording and the committed JSON Resume schema.
- `handle_paste()` now maps both `UnsupportedCanonicalCVFormat` and `CanonicalCVMissing` to a clean `exit 2` with a `"Canonical CV error: ..."` stderr line. The Story 1.4 boundary message is now strictly guarded by reader success, so AC6/AC7 are honored: no LLM SDK, no HTTP client, no `./out/` write occurs on a rejection path.
- Tests cover the safety contract end-to-end: 6 new reader unit tests (incl. case-insensitivity and the `ValueError` subclass check), 6 new CLI tests (3 subprocess + 3 in-process) for the rejection paths, plus the regression guard that valid-env still reaches the Story 1.4 boundary.
- Conftest gained 5 new fixtures (`pdf_canonical_cv`, `pdf_canonical_cv_upper`, `docx_canonical_cv`, `docx_canonical_cv_upper`, `doc_canonical_cv`), all patching `CANONICAL_CV_PATH` in both `jobhunter.config` and `jobhunter.canonical_cv` per the documented two-bind pattern, all writing **zero-byte** files so any regression that lets the reader `json.load` them would raise `JSONDecodeError` (loud failure) rather than silently masking the bug.
- Documentation: `DECISIONS.md` §2 now records the binary-format rejection guarantee as an explicit FR5 enforcement clause; `README.md` Configuration section calls out that PDF/docx are unsupported by extension.

### File List

- `src/jobhunter/canonical_cv.py` (modified — added `UnsupportedCanonicalCVFormat`, extension-based rejection in `read_canonical_cv()`, `__all__` export; review pass: collapsed single-element `_REJECTED_SUFFIXES_PDF` set, renamed `_REJECTED_SUFFIXES_WORD` → `_WORD_SUFFIXES`)
- `src/jobhunter/cli.py` (modified — `handle_paste()` now calls the reader and maps `UnsupportedCanonicalCVFormat` / `CanonicalCVMissing` to clean exit 2; review pass: combined identical except clauses into one tuple-except)
- `tests/conftest.py` (modified — added `_point_canonical_cv_at` helper plus `.pdf` / `.PDF` / `.docx` / `.DOCX` / `.doc` fixtures)
- `tests/unit/test_canonical_cv_reader.py` (modified — 6 new tests for rejection contract; existing 5 tests untouched and still green)
- `tests/integration/test_cli_entry.py` (modified — `_isolated_cli_env` mirrors `canonical-cv.json` into the isolated tree; new `_isolated_cli_env_with_canonical_cv` helper; 6 new tests for CLI rejection paths; review pass: tightened three subprocess assertions from `>= 1` to `== 2` per Task 3 contract)
- `DECISIONS.md` (modified — added "Binary-format rejection" subsection under §2; review pass: footer "Last updated" re-dated to Story 1.3)
- `README.md` (modified — Configuration section now states canonical CV must be text; PDF/docx unsupported; review pass: Status section updated to reflect Stories 1.1–1.3 complete)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — Story 1-3 moved ready-for-dev → in-progress → review → done)

## Change Log

- 2026-05-23 — dev-story 1.3: implemented FR5 binary-format rejection (`.pdf`, `.docx`, `.doc`, case-insensitive) by extension in `read_canonical_cv()` before any read; added typed exception `UnsupportedCanonicalCVFormat(ValueError)`. Wired the reader into `handle_paste()` so rejection and missing-file paths both map to `exit 2` with a `Canonical CV error: ...` stderr line, while the Story 1.4 boundary message stays guarded by reader success. Extended conftest with 5 binary-format fixtures and `_isolated_cli_env` now mirrors `canonical-cv.json` so Story 1.2's valid-env regression guard still holds. 58 tests pass, 2 dotenv-sandbox skips (pre-existing per Story 1.2). No new runtime dependency; no LLM/HTTP/job-board code introduced; no `./out/` write on any rejection path.
- 2026-05-23 — story-automator-review 1.3: 0 CRITICAL / 1 MEDIUM / 4 LOW findings; all auto-fixed. (1) README Status section updated to reflect Stories 1.1–1.3 done. (2) DECISIONS.md footer "Last updated" re-dated to Story 1.3 to acknowledge the new Binary-format-rejection subsection. (3) `_REJECTED_SUFFIXES_PDF` collapsed into a direct `suffix == ".pdf"` check (single-element set added no value); `_REJECTED_SUFFIXES_WORD` renamed `_WORD_SUFFIXES` for clarity. (4) `handle_paste()` collapsed the two identical `except` blocks for `UnsupportedCanonicalCVFormat` / `CanonicalCVMissing` into a single tuple-except clause. (5) Three subprocess rejection tests tightened from `result.returncode >= 1` to `result.returncode == 2` to match the Task-3 contract. 70 tests pass (2 dotenv-sandbox skips pre-existing). Status: review → done.

## Senior Developer Review (AI)

**Reviewer:** dave (claude-opus-4-7[1m]) on 2026-05-23
**Outcome:** Approved — auto-fixes applied

### Summary
Story 1.3 lands the FR5 binary-format rejection cleanly: `read_canonical_cv()` rejects `.pdf`/`.docx`/`.doc` (case-insensitive) by extension **before** any `open()`, and `handle_paste()` maps both `UnsupportedCanonicalCVFormat` and `CanonicalCVMissing` to a clean `exit 2`. All 10 ACs are implemented and exercised by tests. The Story 1.4 boundary message is now strictly guarded by reader success. No new runtime dependency; no LLM/HTTP/job-board code introduced; no `./out/` writes on rejection paths.

### Key Findings

**🟡 MEDIUM (auto-fixed)**
- README Status section claimed only Story 1.1 complete despite 1.2 and 1.3 being done. Updated to reflect Stories 1.1–1.3 complete.

**🟢 LOW (auto-fixed)**
- `DECISIONS.md` "Last updated" footer was stamped Story 1.1 despite the §2 Binary-format-rejection subsection being added for Story 1.3. Re-dated.
- `_REJECTED_SUFFIXES_PDF = {".pdf"}` — single-element set with no semantic value. Collapsed to a direct `suffix == ".pdf"` comparison; renamed the Word suffix set to `_WORD_SUFFIXES`.
- `handle_paste()` had two identical `except` clauses for `UnsupportedCanonicalCVFormat` and `CanonicalCVMissing`. Combined into a single tuple-except for DRYness; behavior unchanged.
- Three subprocess rejection tests asserted `result.returncode >= 1` but Task 3 mandates `2` exactly. Tightened the assertion in the three subprocess tests (`test_paste_subprocess_rejects_pdf_canonical_cv_before_story_1_4`, `test_paste_subprocess_rejects_docx_canonical_cv_before_story_1_4`, `test_paste_subprocess_rejects_missing_canonical_cv_before_story_1_4`) to `== 2` for parity with the in-process `_exits_with_code_two` family.

### Acceptance-Criteria Validation
AC1 ✅ (`test_no_caching_fresh_read_each_call`); AC2 ✅ (`.pdf`/`.PDF`/`.Pdf` reader + CLI tests; "PDF" substring + path in message); AC3 ✅ (`.docx`/`.DOCX`/`.Docx`/`.doc`/`.DOC` reader + CLI tests; "docx" + "Word" substrings); AC4 ✅ (`test_missing_file_raises_canonical_cv_missing`, `test_paste_subprocess_rejects_missing_canonical_cv_before_story_1_4`); AC5 ✅ (`UnsupportedCanonicalCVFormat(ValueError)` in `__all__`, alongside `CanonicalCVMissing`); AC6 ✅ (`handle_paste` order is config → reader → boundary message; rejection short-circuits the boundary); AC7 ✅ (no LLM/HTTP imports in src/; rejection paths produce no `./out/`; `test_cli_paste_does_not_create_out_directory_on_rejection` proves it); AC8 ✅ (17 reader unit tests + 22 CLI tests cover the contract); AC9 ✅ (pyproject.toml diff empty); AC10 ✅ (`test_reader_does_not_validate_jsonresume_schema`).

### Task Completion Audit
Tasks 1–8 all marked [x] and verified against source/tests. No false [x] claims. File List matches git modifications exactly (excluding `_bmad-output/*` per workflow scope).

### Test Coverage Notes
- 17 reader unit tests; 22 CLI integration/in-process tests
- All required ACs covered, plus three robustness add-ons (mixed-case `.Pdf`/`.Docx`, `.DOC` uppercase, "rejection precedes existence check")
- 70 passed, 2 skipped (pre-existing `python-dotenv` sandbox limitation from Story 1.2) — 0 regressions

### Action Items
None. All findings fixed inline.
