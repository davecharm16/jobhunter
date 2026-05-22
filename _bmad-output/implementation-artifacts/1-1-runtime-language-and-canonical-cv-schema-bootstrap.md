# Story 1.1: Runtime, language, and canonical-CV schema bootstrap

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a solo developer (the author),
I want to commit a runtime/language choice and a canonical-CV schema decision to the repo on day one,
so that every later story builds on a stable foundation and I don't relitigate the decision mid-build.

## Acceptance Criteria

1. **AC1 — Runtime/language decision is committed.** The repo contains a top-level `DECISIONS.md` (created at project root) that records:
   - The chosen runtime/language (`python` or `typescript`).
   - A one-paragraph rationale referencing the PRD's criterion ("which the author can move fastest in for a solo nights-and-weekends build" — PRD line 357).
   - The rejected alternative with a one-line reason.
   - A "revisit if" clause naming the specific conditions that would trigger reopening the decision (e.g. "the chosen LLM SDK becomes unreliable in this runtime", "n8n integration ergonomics break down").

2. **AC2 — Runnable project skeleton exists for the chosen runtime.** For **Python** path: `pyproject.toml` at repo root + `src/jobhunter/__init__.py` (PEP 621 layout, `src/` package, Python ≥ 3.11). For **TypeScript** path: `package.json` + `tsconfig.json` at repo root + `src/index.ts` (Node ≥ 20, ESM module, `"type": "module"` in package.json).

3. **AC3 — Standard install command exits 0 on a clean machine.** For Python: `pip install -e .` returns exit code 0. For TypeScript: `npm install` returns exit code 0. The skeleton must NOT yet pull in heavy dependencies (no LLM SDK, no web framework) — only minimal build/test plumbing.

4. **AC4 — Canonical-CV sample file exists at a single configured path.** A sample file `canonical-cv.md` (Python path) or `canonical-cv.json` (TypeScript path) — or `canonical-cv.yaml` if minimal-YAML fallback is chosen — lives at the repo root. The file uses the **JSON Resume schema** as the working assumption (`https://jsonresume.org/schema/`). The path is recorded in a configuration constant (e.g. `CANONICAL_CV_PATH` in a top-level `config.py` or `config.ts`) so downstream stories read from one source.

5. **AC5 — Canonical-CV sample is valid against the chosen schema.**
   - JSON Resume path: validates against `https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json` via a standard validator (e.g. `jsonschema` in Python, `ajv` in TypeScript) — runnable as a one-shot script committed to the repo (e.g. `scripts/validate_canonical_cv.py` or `scripts/validate-canonical-cv.ts`).
   - Minimal-YAML fallback path: a custom validator in `src/` checks the structural shape documented in `DECISIONS.md` and exits non-zero on violation.

6. **AC6 — Schema choice and fallback criterion are explicit in `DECISIONS.md`.** `DECISIONS.md` states the schema choice ("JSON Resume v1.0.0 working assumption" or "minimal custom YAML") AND the criterion that would force a fallback to minimal-YAML (e.g. "JSON Resume cannot represent the `tags` + `highImpact` extensions cleanly per Story 2.1").

7. **AC7 — Canonical-CV reader contract is established for FR4.** A single function (e.g. `read_canonical_cv() -> dict` in Python, or `readCanonicalCv(): CanonicalCV` in TypeScript) is the **only** code path that other stories use to load the canonical CV. It reads from `CANONICAL_CV_PATH` on every invocation with no in-process or on-disk caching. Stub implementation is acceptable in this story; Story 1.3 hardens it.

## Tasks / Subtasks

- [x] **Task 1: Lock in runtime/language decision** (AC: #1)
  - [x] Evaluate Python vs TypeScript against PRD criterion line 357 (which the dev agent can move fastest in for a solo build). Default recommendation: **Python** for richer JSON Schema validation ecosystem and JSON Resume tooling, **unless** the dev agent has stronger TypeScript velocity — in which case TypeScript with `ajv` is equally acceptable per the PRD.
  - [x] Create `/Users/davecharmbulaquena/Desktop/job_hunter/DECISIONS.md` with sections: "Runtime/Language", "Schema", and "Revisit Triggers".
  - [x] Record rejected alternative with one-line reason.

- [x] **Task 2: Bootstrap project skeleton for the chosen runtime** (AC: #2, #3)
  - [x] **If Python:**
    - [x] Create `pyproject.toml` with `[project]` metadata, `name = "jobhunter"`, `version = "0.1.0"`, `requires-python = ">=3.11"`, and `[project.scripts] jobhunter = "jobhunter.cli:main"` (CLI entry wired ahead of Story 1.2; `cli.main` may be a stub that prints usage and exits 2).
    - [x] Create `src/jobhunter/__init__.py` with `__version__ = "0.1.0"`.
    - [x] Create `src/jobhunter/cli.py` with a `main()` stub returning exit code 2.
    - [x] Create `src/jobhunter/canonical_cv.py` with `read_canonical_cv()` stub (Task 5 hardens).
    - [x] Add `[build-system] requires = ["setuptools>=68"]` and `build-backend = "setuptools.build_meta"`.
    - [x] Verify `pip install -e .` exits 0 on a clean venv.
  - [ ] **If TypeScript:** *(N/A — Python path chosen; see DECISIONS.md §1.)*
    - [ ] Create `package.json` with `"name": "jobhunter"`, `"version": "0.1.0"`, `"type": "module"`, `"engines": { "node": ">=20" }`, `"bin": { "jobhunter": "./dist/cli.js" }`, and `"scripts": { "build": "tsc", "validate-cv": "tsx scripts/validate-canonical-cv.ts" }`.
    - [ ] Create `tsconfig.json` with `"target": "ES2022"`, `"module": "NodeNext"`, `"moduleResolution": "NodeNext"`, `"strict": true`, `"outDir": "dist"`, `"rootDir": "src"`.
    - [ ] Create `src/index.ts` exporting a `version` constant and re-exporting from `canonicalCv.ts`.
    - [ ] Create `src/cli.ts` with a stub `main()` printing usage and `process.exit(2)`.
    - [ ] Create `src/canonicalCv.ts` with `readCanonicalCv()` stub.
    - [ ] Verify `npm install` exits 0.

- [x] **Task 3: Author and place the canonical-CV sample file** (AC: #4)
  - [x] Create `canonical-cv.json` at repo root (recommended for both runtimes — JSON Resume's canonical serialization is JSON; the epic mentions `.md` only as a working-assumption stand-in).
  - [x] Populate with a realistic sample using JSON Resume v1.0.0 schema sections: `basics`, `work[]` (≥ 2 entries with `highlights[]`), `skills[]` (≥ 3 entries with `keywords[]`), `projects[]` (≥ 1 entry with `highlights[]`), `education[]` (≥ 1 entry). Use the author's real profile if convenient; otherwise a plausible synthetic example.
  - [x] Add a top-level `CANONICAL_CV_PATH` constant in `src/jobhunter/config.py` (Python) or `src/config.ts` (TypeScript) set to `./canonical-cv.json`.

- [x] **Task 4: Wire JSON Resume schema validation** (AC: #5)
  - [x] **If Python:** Add `jsonschema>=4.21` to `pyproject.toml` `[project] dependencies`. Create `scripts/validate_canonical_cv.py` that downloads (or vendors) `https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json`, loads `canonical-cv.json`, validates, and exits 0 on success or non-zero with a human-readable error on failure. **Vendor the schema** as `schemas/jsonresume-v1.0.0.json` so validation does not require network access (deterministic, offline-safe).
  - [ ] **If TypeScript:** *(N/A — Python path chosen.)* Add `ajv` and `ajv-formats` to `package.json` `devDependencies`. Create `scripts/validate-canonical-cv.ts` that loads `schemas/jsonresume-v1.0.0.json` (vendored), validates `canonical-cv.json`, and exits 0 / non-zero same as above.
  - [x] Run the validator. The sample must pass.

- [x] **Task 5: Implement the canonical-CV reader contract** (AC: #7)
  - [x] **Python:** In `src/jobhunter/canonical_cv.py`, implement `read_canonical_cv() -> dict` that reads `CANONICAL_CV_PATH`, parses JSON, returns the dict. No caching — every call re-reads from disk (FR4). On `FileNotFoundError`, raise a custom `CanonicalCVMissing` exception (Story 1.3 wires this to a clean exit code; for this story, just raise).
  - [ ] **TypeScript:** *(N/A — Python path chosen.)* In `src/canonicalCv.ts`, implement `readCanonicalCv(): CanonicalCV` (define a minimal `CanonicalCV` type matching the populated JSON Resume sections). Use `fs.readFileSync` (sync is fine — the entire pipeline is sequential per the PRD). No caching. Throw a custom `CanonicalCVMissingError` if the file does not exist.
  - [x] PDF/docx rejection logic is **deferred to Story 1.3** — do NOT implement it here. This story stops at the reader stub.

- [x] **Task 6: Finalize `DECISIONS.md` schema section** (AC: #6)
  - [x] Document the schema choice (`JSON Resume v1.0.0 working assumption`).
  - [x] Document the fallback criterion verbatim: "Fall back to minimal custom YAML if JSON Resume cannot cleanly represent the `tags` and `highImpact` per-entry extensions required by Epic 2 Story 2.1 (FR2, FR3)."
  - [x] Note that `tags` and `highImpact` extensions will be added in Story 2.1 — for now, the sample CV uses pure JSON Resume v1.0.0 with no extensions.

- [x] **Task 7: README pointer + smoke verification** (AC: #1–#7)
  - [x] Update the existing `README.md` (currently 1 line: `# jobhunter`) with a one-paragraph project intro and a "Getting started" section linking to `DECISIONS.md` and showing the install command for the chosen runtime.
  - [x] Run the install command from a clean state, then run the canonical-CV validator. Both must exit 0. Capture the commands in the README so a fresh clone can verify.

## Dev Notes

### Critical context

This is the **week-1 walking-skeleton gate**. The story makes two decisions that every later story inherits: runtime/language and canonical-CV schema. It also establishes the single-path canonical-CV reader contract (FR4) that Stories 1.3, 1.5, 2.1, 2.3, 3.1, 3.2, 4.1, and 5.1 all consume. **Get this stable; do not over-build.**

### Architecture-shape requirements (from PRD, since no Architecture document exists)

- **No database in v1.** Filesystem-only persistence. The canonical CV is a single file in version control; per-application outputs are markdown + JSON sidecars under `./out/<slug>/` (later stories).
- **Local-first runtime.** No hosted infra in v1. The CLI runs on the author's machine.
- **Language/runtime decision is YOURS to make in this story.** PRD line 357: "Python or TypeScript are the leading candidates — both have mature LLM SDKs, good markdown tooling, and easy n8n integration. Final choice depends on which the author can move fastest in for a solo nights-and-weekends build."
- **Schema decision is YOURS to make in this story.** Epic 1 description: "Canonical CV schema is JSON Resume schema as the working assumption, with the explicit option to fall back to a minimal custom YAML if JSON Resume does not fit." Default to JSON Resume v1.0.0 unless you find a concrete blocker — and if you do, document it in `DECISIONS.md`.

### FR cross-references this story enables

- **FR1**: Canonical CV as a single markdown/YAML file in version control. (Schema + sample file land here.)
- **FR4**: System reads canonical CV fresh on every pipeline run; no re-import or re-parse step. (Reader contract stub lands here.)
- **FR5**: PDF/docx ingest rejection. (Enforcement deferred to Story 1.3, but the reader API surface anticipates it.)

### What this story does NOT do (scope guardrails)

- ❌ No `.env` handling — that's **Story 1.2**.
- ❌ No `MONTHLY_SPEND_CAP_USD` enforcement — that's **Story 1.2**.
- ❌ No CLI subcommand parsing beyond a usage stub — that's **Story 1.2**.
- ❌ No PDF/docx rejection logic in the reader — that's **Story 1.3**.
- ❌ No JD ingest, no LLM call, no `./out/<slug>/` writes — those are **Stories 1.4, 1.5**.
- ❌ No `tags` or `highImpact` extensions to the canonical CV — those are **Story 2.1**.

If you find yourself implementing any of the above, **stop**. The walking-skeleton gate exists to keep this story small.

### Library / framework choices

- **Python path:** stdlib + `jsonschema>=4.21`. No CLI framework yet (don't add `click` / `typer` in this story — Story 1.2 picks the CLI framework).
- **TypeScript path:** stdlib + `ajv` + `ajv-formats` + `tsx` (dev). No CLI framework yet (don't add `commander` / `yargs` — Story 1.2 picks).
- **Schema:** JSON Resume v1.0.0 (`https://github.com/jsonresume/resume-schema/blob/v1.0.0/schema.json`). **Vendor the schema** into `schemas/jsonresume-v1.0.0.json` — do NOT fetch it at runtime. The PRD's NFR13 (paste mode must always work) implies the validator must work offline.

### File structure (chosen runtime)

**Python:**
```
/
├── DECISIONS.md
├── README.md
├── pyproject.toml
├── canonical-cv.json
├── schemas/
│   └── jsonresume-v1.0.0.json
├── scripts/
│   └── validate_canonical_cv.py
└── src/
    └── jobhunter/
        ├── __init__.py
        ├── cli.py            # stub for Story 1.2
        ├── config.py         # CANONICAL_CV_PATH constant
        └── canonical_cv.py   # read_canonical_cv() stub
```

**TypeScript:**
```
/
├── DECISIONS.md
├── README.md
├── package.json
├── tsconfig.json
├── canonical-cv.json
├── schemas/
│   └── jsonresume-v1.0.0.json
├── scripts/
│   └── validate-canonical-cv.ts
└── src/
    ├── index.ts
    ├── cli.ts                # stub for Story 1.2
    ├── config.ts             # CANONICAL_CV_PATH constant
    └── canonicalCv.ts        # readCanonicalCv() stub
```

### Testing standards

- No formal test framework is required in this story (Story 1.2 picks `pytest` or `vitest`).
- Manual smoke verification is mandatory: from a clean clone, `pip install -e .` (or `npm install`) exits 0, then the validator script exits 0 against the sample `canonical-cv.json`.
- Add a one-line script invocation to the README so the smoke test is reproducible.

### Project Structure Notes

- The repo currently contains only `README.md` (1 line), `.gitignore` (1 line: `.claude/.story-automator-active`), `_bmad/`, `_bmad-output/`, `.claude/`, `.codex/`, `.agent/`, `.agents/`, `.sixth/`, `docs/` (empty), `design_guidelines/` (empty). No source code exists yet.
- `.gitignore` must be extended in this story to include the runtime-specific ignores:
  - **Python path:** add `__pycache__/`, `*.pyc`, `.venv/`, `*.egg-info/`, `dist/`, `build/`.
  - **TypeScript path:** add `node_modules/`, `dist/`, `*.tsbuildinfo`.
- Do **not** add `.env` to `.gitignore` in this story — that lands in Story 1.2 with the rest of the secrets handling.
- Existing `docs/` and `design_guidelines/` folders are unused; leave them alone.
- The `_bmad/` and `_bmad-output/` folders are the BMAD planning surface; do not move or modify them.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Runtime, language, and canonical-CV schema bootstrap] — primary requirements + ACs.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 1: Walking Skeleton (v0.1)] — epic context, FR coverage map, foundational stances.
- [Source: _bmad-output/planning-artifacts/epics.md#Additional Requirements] — language/runtime + schema decisions deferred to first epic story; filesystem-only persistence.
- [Source: _bmad-output/planning-artifacts/prd.md#357] — "Python or TypeScript … which the author can move fastest in for a solo nights-and-weekends build."
- [Source: _bmad-output/planning-artifacts/prd.md#122] — "Canonical-CV schema decided (JSON Resume schema or minimal custom YAML)."
- [Source: _bmad-output/planning-artifacts/prd.md#289] — "Local-first runtime. No hosted infra in v1."
- JSON Resume schema v1.0.0: `https://github.com/jsonresume/resume-schema/blob/v1.0.0/schema.json` (vendor offline).

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) — `claude-opus-4-7[1m]`.

### Debug Log References

- Clean-state smoke (Task 7): `rm -rf .venv src/jobhunter.egg-info && python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/python scripts/validate_canonical_cv.py && .venv/bin/jobhunter` → `INSTALL_EXIT=0`, `VALIDATE_EXIT=0`, `JOBHUNTER_EXIT=2` (CLI stub is intentional).
- Reader contract smoke (Task 5): inline script confirmed `read_canonical_cv()` (a) returns parsed dict, (b) re-reads from disk on every call (mutated file → second call sees sentinel — FR4 satisfied), (c) raises `CanonicalCVMissing` when the file is absent.
- Validator negative test (Task 4): mutating `basics.email` to `"not-an-email"` initially passed because `Draft7Validator` ignores `format` keywords by default. Fixed by wiring `FormatChecker()`; negative case now exits 1 with `at basics/email: 'not-an-email' is not a 'email'`, restored sample exits 0.

### Completion Notes List

- **Runtime/language:** Python 3.11+ chosen. Rationale + revisit triggers in `DECISIONS.md` §1. TypeScript-branch subtasks under Tasks 2/4/5 left unchecked and annotated `(N/A — Python path chosen)`; they are intentionally not implemented per the "If X / If Y" structure of the story.
- **Schema:** JSON Resume v1.0.0 vendored offline at `schemas/jsonresume-v1.0.0.json` (500 lines, fetched from the v1.0.0 tag of `jsonresume/resume-schema`). Validator script reads only the vendored copy — never the network — to satisfy PRD NFR13.
- **Reader contract (FR4):** `read_canonical_cv()` opens `CANONICAL_CV_PATH` on every invocation with no in-process caching. The function returns the raw parsed dict — typing is intentionally loose for this story; richer typing waits for Story 1.3 / 2.1.
- **CLI:** `jobhunter` entry point is wired via `[project.scripts]` but stubbed at exit code 2 with a usage hint; full subcommand parsing is Story 1.2's job.
- **`.gitignore`:** extended with Python-only ignores (`__pycache__/`, `*.pyc`, `.venv/`, `*.egg-info/`, `dist/`, `build/`). `.env` deliberately NOT added — that lands in Story 1.2.
- **Scope discipline:** PDF/docx rejection (Story 1.3), `.env`/cost-cap handling (Story 1.2), and `tags`/`highImpact` extensions (Story 2.1) were intentionally not touched.
- **Pytest adopted early (scope expansion vs. Dev Notes).** Story Dev Notes said "No formal test framework is required in this story (Story 1.2 picks pytest or vitest)." The implementation went further: `pytest>=8.0` is wired as a `[project.optional-dependencies] dev` extra, `[tool.pytest.ini_options]` is configured in `pyproject.toml`, and a 25-test suite under `tests/` covers the config constants, reader contract (FR4), sample-CV shape (AC #4), CLI stub (AC #2), and validator script (AC #5 incl. negative cases). This is consistent with AC #3's explicit "minimal build/test plumbing" allowance, but pre-empts the Story 1.2 framework choice — Story 1.2 should either ratify pytest or explicitly displace it. Smoke commands in the README still document the install + validator flow as the human-runnable gate.

### File List

Created:
- `DECISIONS.md`
- `pyproject.toml` (includes `[project.optional-dependencies] dev = ["pytest>=8.0"]` and `[tool.pytest.ini_options]` — see Completion Notes for the scope-expansion rationale)
- `canonical-cv.json`
- `schemas/jsonresume-v1.0.0.json` (vendored from JSON Resume v1.0.0; offline)
- `scripts/validate_canonical_cv.py`
- `src/jobhunter/__init__.py`
- `src/jobhunter/cli.py`
- `src/jobhunter/config.py`
- `src/jobhunter/canonical_cv.py`
- `tests/conftest.py` (shared fixtures: `tmp_canonical_cv`, `missing_canonical_cv`, `project_root`)
- `tests/unit/__init__.py`
- `tests/unit/test_config.py` (AC #4 — pins `CANONICAL_CV_PATH`, `VENDORED_JSONRESUME_SCHEMA_PATH`, `PROJECT_ROOT`)
- `tests/unit/test_canonical_cv_reader.py` (AC #7 + FR4 — reader contract, no caching, `CanonicalCVMissing`)
- `tests/unit/test_sample_cv.py` (AC #4, #5 — sample-CV shape: ≥2 work + highlights, ≥3 skills + keywords, ≥1 project, ≥1 education)
- `tests/integration/__init__.py`
- `tests/integration/test_cli_entry.py` (AC #2 — `jobhunter` console script + `python -m jobhunter.cli` both exit 2 with usage)
- `tests/integration/test_validate_script.py` (AC #5 — validator exit-code contract: 0 / 1 / 2; isolated workspace per test)

Modified:
- `README.md` (was 1 line; now contains intro, Getting Started incl. `pytest` invocation, repo layout incl. `tests/`)
- `.gitignore` (added Python ignores)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story 1-1: ready-for-dev → in-progress → review)

### Senior Developer Review (AI)

**Reviewer:** dave (BMAD adversarial reviewer) — 2026-05-23
**Outcome:** Approve (with auto-fixes applied)

**Acceptance Criteria — verdict per AC:**
- AC1 (runtime decision in `DECISIONS.md`) — ✅ implemented (DECISIONS.md §1: chosen=Python, rationale references PRD line 357, rejected=TypeScript, three "revisit if" triggers).
- AC2 (runnable Python skeleton) — ✅ implemented (`pyproject.toml` PEP 621, `src/jobhunter/__init__.py`, `requires-python = ">=3.11"`).
- AC3 (`pip install -e .` exits 0 on clean venv) — ✅ verified (re-ran in this review: exit 0).
- AC4 (canonical-CV sample at configured path) — ✅ implemented (`canonical-cv.json` at root, `CANONICAL_CV_PATH` in `src/jobhunter/config.py`).
- AC5 (canonical-CV validates) — ✅ verified (validator exit 0; negative cases exit 1; missing files exit 2 — covered by `tests/integration/test_validate_script.py`).
- AC6 (schema + fallback criterion in `DECISIONS.md`) — ✅ implemented (DECISIONS.md §2, fallback criterion verbatim).
- AC7 (single reader contract for FR4) — ✅ implemented (`read_canonical_cv()`, no caching, raises `CanonicalCVMissing`; `tests/unit/test_canonical_cv_reader.py::test_no_caching_fresh_read_each_call` proves the no-cache property by mutating between calls).

**Findings (all auto-fixed):**
- HIGH — File List omitted all 8 test files + `tests/` structure → File List + Completion Notes updated.
- HIGH — Completion Notes falsely claimed "No test framework yet" while `pyproject.toml` had `pytest>=8.0` + `[tool.pytest.ini_options]` and 25 tests exist → Completion Notes rewritten to describe the actual scope expansion, with a note for Story 1.2 to either ratify or displace pytest.
- MEDIUM — `scripts/validate_canonical_cv.py` hard-coded `Draft7Validator` for a draft-04 schema → switched to `jsonschema.validators.validator_for(schema)` so the validator class tracks the schema's declared draft (now Draft4Validator), still wired with `FormatChecker`. All tests still pass.
- MEDIUM — README Getting Started omitted the pytest invocation despite the suite existing → added step 4 (`pip install -e ".[dev]"` + `pytest`) and `tests/` to the repo-layout block.
- MEDIUM — Change Log row didn't mention the pytest adoption → added `0.1.1` review entry.
- LOW — Weak assertion `"basics/name" in result.stderr or "name" in result.stderr.lower()` in `tests/integration/test_validate_script.py::test_validator_exits_one_on_structural_violation` → tightened to require the path locator `basics/name`.

**Verification after fixes:**
- `pip install -e .` → exit 0.
- `pip install -e ".[dev]"` → exit 0.
- `python scripts/validate_canonical_cv.py` → exit 0 (`ok: …/canonical-cv.json validates against JSON Resume v1.0.0`).
- `jobhunter` (console script) → exit 2 with usage on stderr (stub contract).
- `pytest` → 25 passed in 0.47s (5 reader + 7 config + 5 sample-CV + 3 CLI + 5 validator).

**Out-of-scope items deliberately not fixed:**
- Sample CV contains placeholder values (`+63-900-000-0000`, `https://example.com/davecharm`, "Earlier Role (Synthetic Sample)"). Story Task 3 explicitly permits "a plausible synthetic example" — not a defect.
- `.gitignore` is listed under "Modified" but is technically untracked in git. Dev Notes acknowledge the file pre-existed locally with 1 line; the modification is real on disk even though git sees the whole file as new. Cosmetic.

## Change Log

| Date       | Version | Description                                                                                                  | Author |
| ---------- | ------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| 2026-05-23 | 0.1.0   | Story 1.1: locked in Python runtime + JSON Resume v1.0.0 schema; bootstrapped src/jobhunter skeleton, vendored schema, validator script, reader contract, README + .gitignore; clean-state smoke (install + validate) green. | dave   |
| 2026-05-23 | 0.1.1   | Story 1.1 review auto-fixes: (a) File List now documents the 8-file pytest suite + pyproject pytest config that were added but undocumented; (b) Completion Notes corrected — pytest WAS adopted (was previously falsely claimed deferred to Story 1.2); (c) validator switched from hard-coded `Draft7Validator` to `jsonschema.validators.validator_for(schema)` so it tracks the draft the vendored schema actually declares (draft-04); (d) README Getting Started gained the `pip install -e ".[dev]"` + `pytest` step + tests/ in repo layout; (e) tightened a weak assertion in `tests/integration/test_validate_script.py::test_validator_exits_one_on_structural_violation`. All 25 tests still green; validator still exits 0 on the sample. | review |
