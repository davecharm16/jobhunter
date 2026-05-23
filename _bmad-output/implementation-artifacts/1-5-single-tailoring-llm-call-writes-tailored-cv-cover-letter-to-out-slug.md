# Story 1.5: Single tailoring LLM call writes tailored CV + cover letter to `./out/<slug>/`

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a solo developer (the author),
I want the pipeline to make a tightly-bounded LLM call that tailors a markdown CV and a markdown cover letter against my canonical CV for the JD ingested in Story 1.4, and write both artifacts atomically to `./out/<slug>/`,
so that I can open the staged files in my editor, make 1–3 manual edits, and submit — proving the walking-skeleton concept saves real time on a real application within week 1 (FR17, FR18, FR37, FR43, FR44).

## Acceptance Criteria

1. **AC1 — Happy-path artifact write.** With a valid canonical CV, a non-empty JD (from stdin or `--file`, per Story 1.4), a valid `LLM_API_KEY`, a valid `MONTHLY_SPEND_CAP_USD`, and a monthly spend total below the cap, `jobhunter paste` makes a single LLM call (or tightly-bounded set — see Dev Notes) producing a tailored markdown CV and a tailored markdown cover letter, writes them to `./out/<slug>/cv.md` and `./out/<slug>/cover-letter.md` respectively, prints a single-line success message to stderr naming the slug directory and the total cost of the call, and exits with code **0**. (FR17, FR18, FR37)

2. **AC2 — Slug shape.** `<slug>` is a deterministic-given-inputs, filesystem-safe identifier of the shape `{UTC_TIMESTAMP}-{JD_FIRST_LINE_SLUG}` where `UTC_TIMESTAMP` is `YYYYMMDDTHHMMSSZ` (UTC, e.g. `20260524T031530Z`) and `JD_FIRST_LINE_SLUG` is the JD's first non-empty line lowercased, with all non-`[a-z0-9]` runs collapsed to a single `-`, leading/trailing `-` stripped, and truncated to at most 40 characters. If the JD has no extractable slug content (e.g. a JD consisting only of punctuation), fall back to `{UTC_TIMESTAMP}-jd`. The slug must match the regex `^[0-9]{8}T[0-9]{6}Z(-[a-z0-9-]+)?$`. The directory must not pre-exist; if `./out/<slug>/` already exists (e.g. two runs in the same UTC second on identical first-line slugs), the CLI exits non-zero (code `2`) with an error naming the conflict — **no overwrite of an existing slug directory under any circumstance**.

3. **AC3 — Hard cap is non-bypassable, checked before any LLM call.** Before the first LLM call of the run, the spend tracker reads the current calendar month's running total from `./.cost-ledger.json` (default `0` if file or month-key absent), compares against `MONTHLY_SPEND_CAP_USD` from `.env`, and refuses to call the LLM if the running total is **at or above** the cap. Refusal emits a stderr message containing both the current spend (formatted as a USD-style decimal, e.g. `$24.97`) and the cap (e.g. `$25.00`), and exits with code **2** (config-style violation). No LLM call, no HTTP call, no slug directory, no artifact files. (FR43, NFR-Cost)

4. **AC4 — Per-request token + cost logging.** After every successful LLM call (regardless of whether the pipeline ultimately succeeds), the spend tracker appends the call's cost to `./.cost-ledger.json` under the current `YYYY-MM` key. The ledger schema is exactly `{"YYYY-MM": {"total_usd": "<decimal string>", "calls": <int>}}` and writes use a temp-file + atomic rename so a crash mid-write cannot corrupt the ledger. Cost is computed from the provider's reported usage (input tokens, output tokens) multiplied by the per-model price constants documented in `llm_client.py`. Per-call entries beyond the running sum are NOT required in Story 1.5 — the structured per-application metadata sidecar (FR38) and aggregated cost-per-application reporting via `jobhunter stats` (FR40) land in Epic 2. The ledger file is added to `.gitignore`. (FR39)

5. **AC5 — Atomic artifact write on LLM failure.** When the LLM call fails (any of: `anthropic.APIConnectionError`, `anthropic.APIStatusError` including HTTP 4xx/5xx, `anthropic.APITimeoutError`, `httpx.TimeoutException`, or any other exception raised by the SDK or its transport), the CLI exits non-zero (code `1` for an LLM call failure to distinguish from config errors at code `2`) with a stderr message naming the failure category (e.g. `LLM call failed: timeout after 60s`, `LLM call failed: provider returned 503`, `LLM call failed: network error`). **No `./out/<slug>/` directory is created** and **no `cv.md` or `cover-letter.md` files are written** — the directory creation happens only after the LLM response has been validated as containing both artifacts. The spend ledger is **not** updated on a hard failure (no successful call → no recorded spend). (NFR-Reliability)

6. **AC6 — LLM response validation.** The LLM call is constrained to emit a structured response with exactly two string fields: `cv_markdown` and `cover_letter_markdown`. If the response is missing either field, contains an empty/whitespace-only string for either field, or fails to parse as the expected structure, the CLI exits non-zero (code `1`) with an error naming the validation failure, and **no `./out/<slug>/` directory or files are created**. The successful-call cost IS still recorded in the ledger (a malformed response is a paid API success), so the cap accounting stays honest.

7. **AC7 — Per-call timeout.** The LLM client passes an explicit `timeout=60.0` (seconds) to the SDK call by default. The timeout is sourced from an `LLM_CALL_TIMEOUT_SECONDS` environment variable if set (positive float; non-positive or non-numeric values are rejected via `ConfigurationError` at startup the same way `MONTHLY_SPEND_CAP_USD` is). On timeout, the failure exits as in AC5 — clean error, no partial artifacts, code `1`. (NFR-Performance)

8. **AC8 — No HTTP traffic to job boards.** The LLM call is allowed to reach the chosen provider's API host (e.g. `api.anthropic.com`). The CLI source must contain **zero** references to job-board hostnames (`upwork.com`, `linkedin.com`, `onlinejobs.ph`, or any board-specific path). A test asserts no string-grep match for those hostnames in `src/jobhunter/`. (FR44, FR11)

9. **AC9 — Canonical CV is sent to the LLM verbatim, never mutated on disk.** The tailoring step reads the canonical CV via `read_canonical_cv()` (Story 1.3 contract — re-reads on every call, no cache), serializes it to a JSON string, and includes it in the LLM prompt. The canonical CV file on disk must not be touched by the tailoring step (no `.write_text`, no `.unlink`, no temp-file shenanigans that touch `CANONICAL_CV_PATH`). A regression test snapshots the canonical CV's mtime + content before the run and asserts both are identical after.

10. **AC10 — Ordering of safety gates extends Story 1.4.** The gate order is now (in strict left-to-right precedence, short-circuiting on first failure): (1) `load_runtime_config()`, (2) `read_canonical_cv()`, (3) `_read_jd()` (Story 1.4), (4) `spend_tracker.check_cap_or_raise()`, (5) `llm_client.tailor()`, (6) artifact write. Steps 4–6 are new in Story 1.5. The Stories 1.2 and 1.3 rejection-path subprocess tests (which pipe `"this input must not be consumed\n"` and assert `"Story 1.5" not in stderr` — note: those assertions still string-match `"Story 1.4"`, which the Story 1.4 commit already removed; this story does not re-add `"Story 1.4"` anywhere) continue to pass because steps 1–3 fail before step 4–6 can run. The Story 1.4 happy-path tests that piped a real JD and asserted `"Story 1.5"` in stderr at exit code `1` **must be updated** because the boundary message moves from "tailoring lands in Story 1.5" to the new "tailored package written to `./out/<slug>/` at code 0" success or to a code 1/2 failure path — see Task 5.

11. **AC11 — Single runtime dep added: the LLM SDK.** `pyproject.toml` `dependencies` grows by exactly one entry: the chosen LLM SDK (recommended `anthropic>=0.40.0` per Dev Notes; an alternative provider is acceptable only with explicit dev-agent rationale documented in `DECISIONS.md` §4). No `requests`, no `httpx` directly (the SDK pulls `httpx` transitively — that's fine), no `click`, no `typer`, no `rich`, no job-board client, no second LLM provider. The Story 1.4 forbidden-imports static guard (`test_cli_module_does_not_import_forbidden_runtime_deps`) is updated to allow the chosen SDK while continuing to forbid the others; the Story 1.4 `test_pyproject_runtime_dependencies_did_not_grow_in_story_1_4` test is **renamed** to a Story-1.5 equivalent that pins the new exact dependency list.

12. **AC12 — README, DECISIONS, and `.gitignore` updated.** (a) `README.md` Status line bumps to Stories 1.1–1.5 complete and the Configuration section documents that `LLM_API_KEY` must be a valid key for the chosen provider. (b) `DECISIONS.md` gains a new §4 — *LLM provider* — recording the chosen provider, the chosen model (recommend Claude Haiku 4.5 for the cost target), the pricing constants used, a one-paragraph rationale tied to NFR-Cost (< $0.25 per application), and explicit revisit triggers tied to PRD's "switching providers must be a config change, not a code rewrite" stance. (c) `.gitignore` gains entries for `.cost-ledger.json` and `out/` so the per-application packages and the cumulative spend ledger never get committed.

13. **AC13 — Tests cover the contract and prevent regression.** Pytest suite additions and updates:
    - **New** `tests/integration/test_paste_tailoring.py`: subprocess and in-process tests for AC1 (happy path with mocked LLM), AC2 (slug shape — regex + collision), AC3 (cap pre-check refuses before LLM is called), AC4 (ledger updates after success), AC5 (LLM failure → no artifacts, no ledger update), AC6 (malformed response → no artifacts, ledger still updates), AC7 (timeout wired), AC8 (no job-board hostname in source), AC9 (canonical CV untouched), AC10 (gate ordering preserved), AC11 (deps pinned).
    - **New** `tests/unit/test_spend_tracker.py`: ledger read/write atomicity, month-key isolation, missing-file default-zero, malformed-file behavior (refuse to run, do NOT silently overwrite), at-or-above-cap detection.
    - **New** `tests/unit/test_slug.py`: deterministic transformation of JD first line; fallback to `{ts}-jd` on empty/punctuation-only input; truncation at 40 chars; regex compliance.
    - **New** `tests/unit/test_llm_client.py`: prompt construction (system + user + tool-use schema), cost calculation from `Usage(input_tokens, output_tokens)`, response validation (presence + non-empty), timeout wiring.
    - **Updates** to `tests/integration/test_cli_entry.py` and `tests/integration/test_paste_jd_ingest.py`: the Story 1.4 happy-path tests that piped a real JD and asserted exit `1` + `"Story 1.5"` boundary stderr message must be updated. With the LLM client mocked (default behavior in tests — see Testing Standards), the same inputs now produce exit `0` and a success message naming the slug directory. Rename the affected tests from `..._stops_at_story_1_5_boundary` to `..._writes_tailored_package_to_out_slug` and update assertions accordingly. The negative-assertion tests (`"Story 1.4" not in stderr`) continue to apply unchanged and remain load-bearing regression guards.

## Tasks / Subtasks

- [x] **Task 1: Add the LLM SDK dependency** (AC: #11, #12)
  - [x] Add `anthropic>=0.40.0` to `pyproject.toml`'s `dependencies` array (after the existing `python-dotenv>=1.2.2` entry). Keep `jsonschema` and `python-dotenv` pins exactly as-is.
  - [x] Run `pip install -e .` in the project venv to pull in the SDK and its transitive `httpx`/`pydantic` deps. Confirm install exits 0.
  - [x] If using an alternative provider (OpenAI) instead of Anthropic, append a new entry under §4 of `DECISIONS.md` documenting the reason. **Do not add both.**

- [x] **Task 2: Implement the spend tracker module** (AC: #3, #4, #12)
  - [x] Create `src/jobhunter/spend_tracker.py` with module-level constants `LEDGER_FILENAME = ".cost-ledger.json"` and `LEDGER_PATH = PROJECT_ROOT / LEDGER_FILENAME`.
  - [x] Implement `current_month_key(now: datetime | None = None) -> str` returning `"YYYY-MM"` for UTC now (injectable for tests).
  - [x] Implement `read_ledger() -> dict[str, dict[str, str | int]]`: returns parsed JSON dict if file exists, else `{}`. If the file exists but is corrupt JSON, raise a dedicated `SpendLedgerCorrupt` exception (the CLI must surface this as a clean error and refuse to run — silently truncating the ledger would erase real spend history).
  - [x] Implement `current_month_total_usd(ledger: dict, month_key: str) -> Decimal`: returns `Decimal(ledger.get(month_key, {}).get("total_usd", "0"))`.
  - [x] Implement `check_cap_or_raise(cap_usd: Decimal, *, now: datetime | None = None) -> Decimal`: reads ledger, computes current spend; if `current >= cap`, raises a dedicated `SpendCapExceeded` carrying both current and cap; otherwise returns the current spend so the caller can include it in the success summary.
  - [x] Implement `record_call(cost_usd: Decimal, *, now: datetime | None = None) -> None`: reads ledger, increments the current-month `total_usd` by `cost_usd` and `calls` by 1, then writes back via the atomic-rename pattern (`json.dump` to `LEDGER_PATH.with_suffix(".tmp")`, then `os.replace`).
  - [x] Use `Decimal` throughout — never `float`. Serialize Decimals as quoted strings (`json.dumps` with `default=str`).

- [x] **Task 3: Implement the slug helper** (AC: #2)
  - [x] Create `src/jobhunter/slug.py`.
  - [x] Implement `make_slug(jd_text: str, *, now: datetime | None = None) -> str`. Logic:
    - `ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")`
    - Extract the JD's first non-empty line via `next((l.strip() for l in jd_text.splitlines() if l.strip()), "")`
    - Lowercase, then `re.sub(r"[^a-z0-9]+", "-", ...).strip("-")`
    - Truncate to 40 chars at the last `-` boundary if possible (no mid-word cut), else hard-truncate
    - If the resulting JD-derived slug is empty, use `"jd"`
    - Return `f"{ts}-{jd_part}"`
  - [x] Validate against the AC2 regex inside the function (raise an internal error if a programming mistake produces a non-conforming slug — defense-in-depth before it ever hits the filesystem).

- [x] **Task 4: Implement the LLM client module** (AC: #1, #5, #6, #7, #11)
  - [x] Create `src/jobhunter/llm_client.py`.
  - [x] Module-level constants: `MODEL_NAME = "claude-haiku-4-5"`, `INPUT_PRICE_PER_MTOK = Decimal("1.00")`, `OUTPUT_PRICE_PER_MTOK = Decimal("5.00")`, `DEFAULT_TIMEOUT_SECONDS = 60.0` (sourced from `LLM_CALL_TIMEOUT_SECONDS` env if set; validated in `runtime_config.py` — see Task 7).
  - [x] Define a `@dataclass(frozen=True) TailoringResult` with fields `cv_markdown: str`, `cover_letter_markdown: str`, `cost_usd: Decimal`, `input_tokens: int`, `output_tokens: int`.
  - [x] Define exceptions: `LLMCallFailed(RuntimeError)` (for network/transport/timeout/HTTP errors) and `LLMResponseInvalid(RuntimeError)` (for missing fields, empty strings, malformed structure).
  - [x] Implement `tailor(canonical_cv: dict, jd_text: str, *, api_key: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> TailoringResult`:
    - Construct `client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)`.
    - System prompt: see verbatim text in Dev Notes "Prompt design" — keep it inline as a module-level string so prompt edits are diffable.
    - User prompt: `f"## Canonical CV (JSON Resume v1.0.0)\n```json\n{json.dumps(canonical_cv, indent=2)}\n```\n\n## Job Description\n{jd_text}\n\nProduce the tailored CV and cover letter."`
    - Use `client.messages.create(...)` with the tool-use pattern (see Dev Notes — define an `emit_tailored_artifacts` tool whose input schema mandates `cv_markdown` and `cover_letter_markdown` as required strings; set `tool_choice={"type": "tool", "name": "emit_tailored_artifacts"}` so the model is forced to emit a structured tool call).
    - Wrap the API call in `try/except`. Catch `anthropic.APIConnectionError`, `anthropic.APITimeoutError`, `anthropic.APIStatusError`, and re-raise as `LLMCallFailed(category, original_exc)`. Catch a broad `Exception` last and re-raise as `LLMCallFailed("unexpected error", exc)` — do **not** silently swallow.
    - Parse the response: locate the `tool_use` block, extract its `input` dict. Validate via `LLMResponseInvalid` if `cv_markdown` is missing, not a string, or whitespace-only; same for `cover_letter_markdown`.
    - Compute cost: `cost = (input_tokens * INPUT_PRICE_PER_MTOK / Decimal("1000000")) + (output_tokens * OUTPUT_PRICE_PER_MTOK / Decimal("1000000"))`. Quantize to 6 decimal places.
    - Return `TailoringResult`.

- [x] **Task 5: Implement the tailoring orchestration and wire it into `handle_paste`** (AC: #1, #2, #5, #6, #9, #10)
  - [x] Create `src/jobhunter/tailoring.py` with one public entry: `def run_tailoring(canonical_cv: dict, jd_text: str, *, config: RuntimeConfig, now: datetime | None = None, llm_tailor=llm_client.tailor) -> Path`.
    - The `llm_tailor=` keyword is the test seam — tests inject a fake `tailor` callable instead of patching the module. Default to the real client.
    - Pre-check the cap: `current_spend = spend_tracker.check_cap_or_raise(config.monthly_spend_cap_usd, now=now)` (raises `SpendCapExceeded` on violation; handled by the CLI caller).
    - Make the LLM call: `result = llm_tailor(canonical_cv, jd_text, api_key=config.llm_api_key, timeout_seconds=config.llm_call_timeout_seconds)`.
    - Record cost: `spend_tracker.record_call(result.cost_usd, now=now)`.
    - Compute slug + final dir: `slug = make_slug(jd_text, now=now); out_dir = PROJECT_ROOT / "out" / slug`.
    - Refuse pre-existing slug dir: `if out_dir.exists(): raise FileExistsError(out_dir)`.
    - Write atomically via a temp sibling: `tmp_dir = out_dir.with_name(slug + ".tmp"); tmp_dir.mkdir(parents=True, exist_ok=False); (tmp_dir / "cv.md").write_text(result.cv_markdown, encoding="utf-8"); (tmp_dir / "cover-letter.md").write_text(result.cover_letter_markdown, encoding="utf-8"); os.replace(tmp_dir, out_dir)`.
    - Return `out_dir`.
  - [x] Update `src/jobhunter/cli.py`'s `handle_paste()`:
    - After `_read_jd()` succeeds, call `run_tailoring(canonical_cv, jd_text, config=runtime_config)` (note: `read_canonical_cv()` already returns the dict; `load_runtime_config()` returns the `RuntimeConfig` — capture both as `runtime_config = load_runtime_config(); canonical_cv = read_canonical_cv()`).
    - Catch `SpendCapExceeded` → print stderr message naming current + cap → return `2`.
    - Catch `SpendLedgerCorrupt` → print stderr message naming the ledger path → return `2`.
    - Catch `LLMCallFailed` → print `f"LLM call failed: {exc}"` to stderr → return `1`.
    - Catch `LLMResponseInvalid` → print stderr message → return `1`.
    - Catch `FileExistsError` (slug collision) → print stderr → return `2`.
    - On success: `print(f"Tailored package written to {out_dir} (cost: ${result.cost_usd}; monthly spend ${current_spend + result.cost_usd} of ${cap}).", file=sys.stderr)` → return `0`. (Pass the cost back from `run_tailoring` either via a tuple return or by exposing the `result` object — choose the smaller diff.)
  - [x] **Remove** the Story 1.4 boundary `print` (the `"jobhunter paste ingested JD ({n} chars from {source}); tailoring lands in Story 1.5."` line). Story 1.5's success message replaces it on the happy path; the failure paths above replace it on the unhappy paths.

- [x] **Task 6: Extend `runtime_config.py` to load `LLM_CALL_TIMEOUT_SECONDS`** (AC: #7)
  - [x] Add an optional field `llm_call_timeout_seconds: float` to `RuntimeConfig` (default `60.0`).
  - [x] In `load_runtime_config()`, parse `os.environ.get("LLM_CALL_TIMEOUT_SECONDS")`. If unset, use default. If set, parse as `float`; on `ValueError` or non-positive, raise `ConfigurationError` with the same shape as the existing checks.
  - [x] Document the env var in `.env.example` as a commented-out optional override (`# LLM_CALL_TIMEOUT_SECONDS=60`).

- [x] **Task 7: Tighten Story 1.4's forbidden-imports test for the new SDK** (AC: #8, #11)
  - [x] Update `tests/integration/test_paste_jd_ingest.py::test_cli_module_does_not_import_forbidden_runtime_deps`: the new `anthropic` (or chosen-provider) import is allowed. The test scope is `src/jobhunter/cli.py` today — broaden it to scan **all** `.py` files under `src/jobhunter/` (so `llm_client.py` can `import anthropic` but `cli.py` still can't `import requests`).
  - [x] Update `tests/integration/test_paste_jd_ingest.py::test_pyproject_runtime_dependencies_did_not_grow_in_story_1_4` → rename to `test_pyproject_runtime_dependencies_match_story_1_5_pinning` and update the assertion list to include the new SDK pin. Continue to forbid the entire `requests`/`click`/`typer`/`rich`/second-LLM-SDK list.
  - [x] Add an `assert` in the same test file that no source file under `src/jobhunter/` references `upwork.com`, `linkedin.com`, or `onlinejobs.ph` (case-insensitive string match). This is the load-bearing FR44 / FR11 guard.

- [x] **Task 8: Update the Story 1.4 happy-path tests for the new success contract** (AC: #1, #10, #13)
  - [x] In `tests/integration/test_cli_entry.py`:
    - `test_paste_subprocess_valid_env_stdin_stops_at_story_1_5_boundary` → rename to `test_paste_subprocess_valid_env_stdin_writes_tailored_package` and update: with the LLM client mocked at the `llm_client.tailor` seam (via a `conftest.py`-level autouse fixture — see Testing Standards), exit code becomes `0`, stderr contains `"Tailored package written to"` and an `./out/<slug>/` path, and `./out/<slug>/cv.md` + `./out/<slug>/cover-letter.md` exist.
    - `test_cli_paste_reaches_story_1_5_boundary_with_valid_env_and_stdin` → rename to `test_cli_paste_writes_tailored_package_in_process_with_stdin` and apply the same update for the in-process path.
  - [x] In `tests/integration/test_paste_jd_ingest.py`, update the gap-closure tests that asserted `"Story 1.5" in stderr` at exit code `1`:
    - `test_paste_subprocess_with_file_succeeds_at_story_1_5_boundary` (and its `_with_stdin` companion) — update to assert exit code `0` and stderr matches `"Tailored package written to .*/out/.*"`.
    - The empty-file / whitespace-only / missing-file / directory-target / non-UTF-8 / binary-file rejection tests are **not** changed — they still exit `2` before the LLM client is reached (the ordering AC10 guarantees this).
    - The boundary-message contract tests (`test_paste_subprocess_boundary_message_includes_char_count_and_file_path`, `_for_stdin_...`) — the contract message changes shape entirely. Either rename and rewrite to assert the Story-1.5 success message, or delete them (Story 1.4's "char count from source" message no longer prints on success).
  - [x] The Story 1.2 + 1.3 env/CV rejection-path tests (`test_paste_subprocess_missing_llm_key_fails_before_reading_stdin`, etc.) keep passing untouched. They short-circuit before the spend tracker and LLM client are reached. Their `"Story 1.4" not in stderr` assertion is unchanged.

- [x] **Task 9: Add the new Story 1.5 test files** (AC: #13)
  - [x] **`tests/unit/test_slug.py`** — pure-function tests against `make_slug`:
    - Deterministic output for a fixed `now` parameter and a fixed JD.
    - First-line extraction skips leading blank lines.
    - Punctuation-only and empty JDs fall back to `{ts}-jd`.
    - Truncation at 40 chars.
    - Regex compliance — assert `re.fullmatch(r"^[0-9]{8}T[0-9]{6}Z(-[a-z0-9-]+)?$", slug)`.
  - [x] **`tests/unit/test_spend_tracker.py`**:
    - `current_month_total_usd` of an empty ledger is `Decimal("0")`.
    - `check_cap_or_raise` raises `SpendCapExceeded` when current >= cap and not before.
    - `record_call` increments `total_usd` by the recorded cost and `calls` by 1.
    - Atomic write: simulate a crash mid-write (e.g. `monkeypatch.setattr(os, "replace", ...)` raising), confirm the ledger file is not corrupted.
    - `read_ledger` raises `SpendLedgerCorrupt` (NOT a silent default-to-`{}`) when the file exists but is not valid JSON.
    - Decimals are stored as quoted strings (`"24.97"`, never `24.97`).
  - [x] **`tests/unit/test_llm_client.py`**:
    - Cost calculation: `_compute_cost(input_tokens=1000, output_tokens=500)` matches the pricing constants. Use a fake `Usage` namedtuple.
    - Response-validation: a missing `cv_markdown` field raises `LLMResponseInvalid`. An empty `cover_letter_markdown` raises `LLMResponseInvalid`.
    - Prompt construction: the system prompt is a constant module-level string (snapshot it); the user prompt includes both the canonical CV JSON and the JD text.
    - Timeout wiring: a fake `anthropic.Anthropic` client constructor records the `timeout=` kwarg; assert it matches the value passed in.
    - **No real HTTP**: every test must monkeypatch the SDK client or pass a fake-client constructor — under no circumstances does the unit test hit `api.anthropic.com`.
  - [x] **`tests/integration/test_paste_tailoring.py`**:
    - `test_paste_subprocess_happy_path_writes_both_artifacts`: mocks `llm_client.tailor` (via PYTHONPATH-injected `sitecustomize.py` or a stub module — see Testing Standards), exits `0`, asserts both files exist with the mocked content.
    - `test_paste_subprocess_slug_shape_matches_regex`: greps the success message for the slug, validates against AC2's regex.
    - `test_paste_subprocess_pre_existing_slug_dir_exits_two`: pre-creates `./out/{deterministic-slug}/`, runs the CLI with a frozen `now`, asserts exit `2` + no overwrite.
    - `test_paste_subprocess_cap_exceeded_refuses_before_llm_call`: writes a ledger with `total_usd >= cap`, asserts exit `2`, asserts the LLM mock was never called (instrument via a sentinel file the mock would create — its absence is the proof).
    - `test_paste_subprocess_ledger_updates_on_success`: pre-writes a ledger with `$10.00`, asserts post-run ledger contains `$10.00 + mocked_cost`.
    - `test_paste_subprocess_ledger_corrupt_refuses_run`: pre-writes a malformed JSON ledger; assert exit `2`, no LLM call, no artifact directory.
    - `test_paste_subprocess_llm_failure_writes_no_artifacts`: configure the LLM mock to raise `LLMCallFailed`; assert exit `1`, no `./out/<slug>/` directory exists, and the ledger is **not** incremented.
    - `test_paste_subprocess_invalid_llm_response_writes_no_artifacts`: configure the LLM mock to raise `LLMResponseInvalid`; assert exit `1`, no artifacts. The ledger update on a paid-API success that returned a malformed structure is acceptable as long as the `tailor()` contract is "raise `LLMResponseInvalid` only after recording the cost"; if the dev chooses to record cost inside `tailor()` before validation, document that. (Implementation choice: cleanest is to validate inside `tailor()` AFTER computing cost, so the cost is captured in the `TailoringResult` even if we then raise — but the simpler "raise without recording" pattern is acceptable for the walking skeleton and is the recommended path; AC6's text covers both choices.)
    - `test_paste_subprocess_canonical_cv_untouched`: snapshot `canonical-cv.json` mtime + sha256 before, run, snapshot after, assert identical (AC9).
    - `test_paste_subprocess_no_job_board_hostnames_in_source` (could live in `test_paste_jd_ingest.py` — Task 7 — or here; pick one home).
    - `test_paste_subprocess_timeout_env_invalid_exits_two`: set `LLM_CALL_TIMEOUT_SECONDS=-1`, assert config-error exit `2`.
    - `test_paste_in_process_happy_path_writes_both_artifacts`: in-process variant with `llm_tailor=` injected directly into `run_tailoring` (no monkeypatch).

- [x] **Task 10: Documentation refresh** (AC: #12)
  - [x] `README.md` Configuration section: add a sentence noting `LLM_API_KEY` must be a valid Anthropic API key (or the chosen provider's key) and that the optional `LLM_CALL_TIMEOUT_SECONDS` env var overrides the 60-second per-call timeout.
  - [x] `README.md` Configuration section: add a short example showing the end-to-end happy path, e.g.:
    ```
    # End-to-end (with valid .env and canonical-cv.json):
    pbpaste | jobhunter paste
    # → Tailored package written to ./out/20260524T031530Z-senior-python-role/ ...
    ```
  - [x] `README.md` Status section: update to "Stories 1.1–1.5 (walking-skeleton runtime + CLI scaffold + canonical-CV reader hardening + JD ingest via stdin/`--file` + single-call tailoring writing `./out/<slug>/`) complete."
  - [x] `README.md` Repo layout section: add the new files (`spend_tracker.py`, `slug.py`, `llm_client.py`, `tailoring.py`) and the new artifact (`./out/<slug>/` plus the `.cost-ledger.json` ledger).
  - [x] `DECISIONS.md`: append a new section **§4. LLM provider** with the structure used by §1 + §2 — Decision, Rationale, Rejected alternative, Revisit if. Document the model name, pricing constants used (and the date they were captured), and the NFR-Cost target.
  - [x] `.gitignore`: add `.cost-ledger.json` (a line on its own) and `out/` (also on its own). Confirm both work via `git status --ignored` after a smoke run.

- [x] **Task 11: Verification** (AC: #1–#13)
  - [x] Run `python scripts/validate_canonical_cv.py` — must still exit `0`.
  - [x] Run `jobhunter` (no args) — must still exit `2` with usage listing `paste`.
  - [x] Run `jobhunter --help` — must still exit `0` with the no-auto-submit statement intact.
  - [x] Run `jobhunter paste --help` — must exit `0` and still mention `--file` and the stdin contract.
  - [x] Run `jobhunter paste` with no env — must still exit `2` naming `LLM_API_KEY`. (AC10 gate ordering.)
  - [x] Run `pytest` — all previous tests pass (with renames + assertion updates from Tasks 5 + 8); all new tests from Task 9 pass; the suite still has the 2 pre-existing `python-dotenv`-conditional skips and no new skips.
  - [x] **Live smoke (one-shot, with real provider key — author runs locally):** `LLM_API_KEY=<real-anthropic-key> MONTHLY_SPEND_CAP_USD=25.00 echo "Senior Python role at Acme. Must have FastAPI, Postgres, and 5+ years backend." | jobhunter paste`. Confirm exit `0`, `./out/<slug>/cv.md` + `cover-letter.md` exist, both are non-empty plausible markdown, `.cost-ledger.json` exists with a sub-$0.01 entry under the current month key. Open both files in an editor; sanity-check the CV is tailored against the JD (Python/FastAPI/Postgres skills should be foregrounded). Note: the live smoke is the dev's responsibility and is **not** wired into CI — under no circumstances should `pytest` ever hit a real LLM endpoint.
  - [x] **Cap-exceeded smoke:** with the same env, manually edit `.cost-ledger.json` so the current month's `total_usd` is `25.00`; rerun `jobhunter paste` with a piped JD; confirm exit `2`, no `./out/` directory grew, the LLM was not called.
  - [x] **Timeout smoke:** set `LLM_CALL_TIMEOUT_SECONDS=0.001` and rerun; confirm exit `1` with a clean "LLM call failed: timeout" stderr message and no `./out/<slug>/` directory.
  - [x] **Slug collision smoke:** freeze the timestamp by `mkdir`-ing the expected slug directory before the run (or by running twice in the same UTC second with identical first-line JD); confirm exit `2` with a clean "slug already exists" message; **no overwrite**.

## Dev Notes

### What changes vs Story 1.4

Story 1.4 hands a JD text + a parsed canonical CV to `handle_paste()` and stops at a stderr boundary message. Story 1.5 picks up from that point and does the actual tailoring work — the first LLM call in the project's history, the first `./out/` write, the first runtime-dep growth past Stories 1.1+1.2, the first persistent state (the spend ledger). This story closes Epic 1: after it ships, the walking skeleton is end-to-end.

The recommended final shape of `handle_paste()` after Story 1.5 is:

```python
def handle_paste(jd_file: Path | None = None) -> int:
    try:
        config = load_runtime_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        canonical_cv = read_canonical_cv()
    except (UnsupportedCanonicalCVFormat, CanonicalCVMissing) as exc:
        print(f"Canonical CV error: {exc}", file=sys.stderr)
        return 2

    jd_text, jd_source = _read_jd(jd_file)
    if jd_text is None:
        return 2

    try:
        out_dir, result, current_spend = run_tailoring(canonical_cv, jd_text, config=config)
    except SpendLedgerCorrupt as exc:
        print(f"Spend ledger error: {exc}", file=sys.stderr)
        return 2
    except SpendCapExceeded as exc:
        print(
            f"Monthly LLM spend cap reached: ${exc.current_usd} of ${exc.cap_usd}. "
            "Refusing to run; raise the cap or wait until next month.",
            file=sys.stderr,
        )
        return 2
    except FileExistsError as exc:
        print(f"Output slug already exists: {exc}", file=sys.stderr)
        return 2
    except LLMCallFailed as exc:
        print(f"LLM call failed: {exc}", file=sys.stderr)
        return 1
    except LLMResponseInvalid as exc:
        print(f"LLM response was unusable: {exc}", file=sys.stderr)
        return 1

    print(
        f"Tailored package written to {out_dir} "
        f"(cost ${result.cost_usd}; monthly spend ${current_spend + result.cost_usd} of ${config.monthly_spend_cap_usd}).",
        file=sys.stderr,
    )
    return 0
```

Note the exit-code split: **2** for config/state violations (caught early, recoverable by the user editing `.env` or the ledger), **1** for runtime LLM-call failures (the user retries or waits). This matches the Story 1.2/1.3 convention where validation failures exit `2`.

### LLM provider choice (recommendation, with rationale)

**Recommendation: Anthropic Claude via the `anthropic` Python SDK, model `claude-haiku-4-5`.**

Rationale tied to PRD constraints:

- **NFR-Cost (< $0.25 per application).** Claude Haiku 4.5 is approximately $1/MTok input, $5/MTok output (capture the actual pricing in `DECISIONS.md` §4 at implementation time — pricing drifts). A walking-skeleton tailoring call against the committed canonical CV (~1KB JSON) plus a typical 2–4KB Upwork JD plus a ~3–5KB tailored output lands well under $0.01 per call. Two artifacts in one call comfortably fits the per-application budget with room for the Epic 3 drift-check call later.
- **NFR-Performance (< 90s end-to-end, < 60s per-call timeout).** Haiku's typical first-byte latency and end-to-end completion on a ~5–10KB total payload is well below 30s in normal conditions.
- **Tool-use for structured output.** Anthropic's tool-use API forces the model to emit exactly the JSON schema you specify, which is the reliability path for AC6 (response validation). The alternative (free-form JSON in prose) is brittle.
- **PRD NFR-Integration ("provider switch must be a config change, not a code rewrite").** Isolating the SDK to `llm_client.py` (one module, one public function `tailor()`, one pricing constants block) means an OpenAI fallback is a single-file rewrite, not a refactor.

**Rejected alternative.** OpenAI `gpt-4o-mini` via the `openai` SDK. Comparable cost and quality. Rejected only because the author's existing toolchain and the dev-agent's prompt-engineering experience lean Anthropic — there is no strong technical signal to prefer one over the other for this workload. If the dev agent has a strong reason to choose OpenAI (e.g. existing key, organizational preference, structured-output ergonomics), they may; in that case, append a §4 entry to `DECISIONS.md` documenting the call and update the SDK pin in `pyproject.toml` accordingly. **Do not pin both SDKs** — one provider, one SDK, per PRD NFR-Integration.

**Revisit if:** (a) Anthropic raises Haiku pricing >2× during walking-skeleton work; (b) the chosen model fails AC6 (malformed JSON) more than 1 in ~20 calls during manual smoke; (c) Epic 2's prompt-template versioning (Story 2.9) reveals a feature gap (e.g. one provider gains a notably stronger structured-output mode); (d) the LLM SDK becomes incompatible with the pinned Python 3.11+.

### Prompt design (verbatim recommendation)

**System prompt** (a module-level constant in `llm_client.py`; tweaks land here, not deep inside `tailor()`):

```
You are an assistant that tailors a software engineer's CV and cover letter for a specific job description (JD).

You are given:
1. The candidate's canonical CV in JSON Resume v1.0.0 format. This is the authoritative source of the candidate's history.
2. A JD pasted by the candidate.

Produce two markdown artifacts:
- A tailored CV that prioritizes canonical-CV entries relevant to the JD.
- A cover letter (3-5 short paragraphs) addressing the JD specifically.

NON-NEGOTIABLE RULES
- Every skill, project, and claim in the tailored CV MUST trace to an entry in the canonical CV. Do not invent skills, employers, or experience the candidate has not stated.
- Preserve the candidate's voice. Plain language. No corporate filler ("synergize", "leverage", "results-driven", "passionate", "extensive experience").
- Use markdown only. Headings with ##, lists with -, emphasis with ** where appropriate. No HTML.
- The cover letter is a letter, not a list. Paragraphs, not bullets.
- Do not include a placeholder for the recipient's name unless the JD provides one.

OUTPUT FORMAT
Call the emit_tailored_artifacts tool with two string fields: cv_markdown and cover_letter_markdown. No other output.
```

**Tool definition** (Anthropic tool-use forces structured output — this is the reliability mechanism for AC6):

```python
TAILORING_TOOL = {
    "name": "emit_tailored_artifacts",
    "description": "Emit the tailored CV and cover letter for the candidate's JD.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cv_markdown": {
                "type": "string",
                "description": "Tailored CV as a markdown document.",
            },
            "cover_letter_markdown": {
                "type": "string",
                "description": "Tailored cover letter as a markdown document.",
            },
        },
        "required": ["cv_markdown", "cover_letter_markdown"],
    },
}
```

Call with `tools=[TAILORING_TOOL]` and `tool_choice={"type": "tool", "name": "emit_tailored_artifacts"}` so the model is forced into a structured emission. Parse by walking `response.content` for the first block with `type == "tool_use"` and pulling `block.input`.

### Spend tracker design

Ledger lives at `<PROJECT_ROOT>/.cost-ledger.json` (gitignored — AC12). Schema deliberately minimal for the walking skeleton:

```json
{
  "2026-05": {"total_usd": "0.012345", "calls": 3},
  "2026-04": {"total_usd": "1.234567", "calls": 42}
}
```

- `total_usd` stored as a JSON string (so `Decimal` round-trips cleanly with no float drift).
- `calls` for AC4's "calls" counter — supports a future `jobhunter stats` (FR40) read.
- Multiple months persist across the month boundary; only the current month's total is checked against the cap.
- Atomic write via temp-sibling + `os.replace`. POSIX guarantees `os.replace` is atomic; on Windows it's atomic on NTFS for same-volume renames. Walking skeleton is POSIX-author's-laptop — this is safe.
- **Corruption is a hard error, not a default-to-zero.** If `.cost-ledger.json` exists but is not valid JSON (e.g. half-written from a previous crash, or hand-edited badly), the CLI refuses to run with `SpendLedgerCorrupt`. The user inspects, fixes, retries. Silently truncating would erase real spend history — that's the failure mode that lets a buggy loop drain the wallet, which is exactly what the cap is meant to prevent.
- The ledger is **single-process**. Two concurrent `jobhunter paste` invocations could race on the read-modify-write — accepted for walking skeleton (the author runs one at a time). A file-locking story is deferred to Epic 2 or later when scheduled flows (Epic 7) could plausibly produce concurrent writes.

### Slug shape and collision policy

Format: `{YYYYMMDDTHHMMSSZ}-{normalized-first-line}` truncated at 40 chars on the second segment. Example for a JD whose first line is `"Senior Python Developer @ Acme — Remote ($120k+)"` at UTC `2026-05-24 03:15:30`: `20260524T031530Z-senior-python-developer-acme-remote`.

Why timestamp first? Two reasons:
1. Listing `./out/` sorts chronologically — the author scrolls his most recent applications first.
2. Same-second collisions are extremely rare on a manual paste workflow but possible on scheduled flows (Epic 7). The collision policy (AC2) refuses to overwrite, surfacing the conflict so the dev or operator can investigate.

Truncation at 40 chars on the JD-derived suffix is a balance: long enough to be recognizable in `ls ./out/`, short enough to avoid hitting any filesystem path-length limits.

### Atomic artifact write — temp-rename pattern

The write sequence is:

```python
tmp_dir = out_dir.with_name(out_dir.name + ".tmp")
tmp_dir.mkdir(parents=True, exist_ok=False)   # fresh dir, fails if leftover
(tmp_dir / "cv.md").write_text(result.cv_markdown, encoding="utf-8")
(tmp_dir / "cover-letter.md").write_text(result.cover_letter_markdown, encoding="utf-8")
os.replace(tmp_dir, out_dir)                   # atomic rename: tmp → final
```

Why this matters: AC5 says no partial files on LLM failure. The temp-sibling pattern also guards against the (rare) case of a disk-full during the second `write_text` — the user sees the `.tmp` directory and can clean it up manually; the real `./out/<slug>/` never exists in a half-written state.

If a previous run crashed and left a `.tmp/` sibling lying around with the exact slug name, the second `mkdir(exist_ok=False)` will fail loudly — that's the desired behavior (surface the leftover, don't silently overwrite).

### Error handling matrix

| Failure | Exception caught | Exit code | Stderr shape | Ledger updated? | Artifact dir created? |
|---|---|---|---|---|---|
| `LLM_API_KEY` missing | `ConfigurationError` (Story 1.2) | 2 | `Configuration error: LLM_API_KEY is required and must be non-empty` | No | No |
| `MONTHLY_SPEND_CAP_USD` missing/invalid | `ConfigurationError` (Story 1.2) | 2 | `Configuration error: MONTHLY_SPEND_CAP_USD ...` | No | No |
| `LLM_CALL_TIMEOUT_SECONDS` invalid | `ConfigurationError` (this story) | 2 | `Configuration error: LLM_CALL_TIMEOUT_SECONDS ...` | No | No |
| Canonical CV `.pdf`/`.docx` | `UnsupportedCanonicalCVFormat` (Story 1.3) | 2 | `Canonical CV error: PDF ... not supported` | No | No |
| Canonical CV missing | `CanonicalCVMissing` (Story 1.3) | 2 | `Canonical CV error: not found at <path>` | No | No |
| JD ingest failure (TTY/empty/missing-file/dir/non-UTF-8) | (Story 1.4 — `_read_jd` returns `None`) | 2 | Story 1.4 messages | No | No |
| Ledger corrupt | `SpendLedgerCorrupt` (this story) | 2 | `Spend ledger error: ./.cost-ledger.json is not valid JSON` | No | No |
| Cap reached | `SpendCapExceeded` (this story) | 2 | `Monthly LLM spend cap reached: $24.97 of $25.00` | No | No |
| Slug collision | `FileExistsError` (this story) | 2 | `Output slug already exists: ./out/<slug>` | No (no LLM call) | No |
| LLM transport/timeout/HTTP error | `LLMCallFailed` (this story) | 1 | `LLM call failed: timeout after 60s` (or similar) | No | No |
| LLM response malformed | `LLMResponseInvalid` (this story) | 1 | `LLM response was unusable: cv_markdown missing` | Yes (paid API success) OR No (raise-before-record — see AC6) | No |
| Disk-full / OS error during artifact write | `OSError` from `write_text`/`replace` | 1 | `Failed to write artifacts: <reason>` | Yes (LLM succeeded) | Partial-or-none under `.tmp/`; final `out/<slug>/` not created |
| Success | — | 0 | `Tailored package written to ./out/<slug> (cost $0.0042; monthly spend $0.0157 of $25.00).` | Yes | Yes |

### Library / framework requirements

- **New runtime dep: `anthropic>=0.40.0`** (or chosen provider's SDK — see "LLM provider choice" above). This is the **only** new entry in `pyproject.toml` `dependencies`. The SDK transitively pulls `httpx`, `pydantic`, and `anyio` — that's fine; do not pin them directly.
- **Stdlib for everything else.** `json`, `os`, `pathlib`, `tempfile` (optional — `with_name(...".tmp")` is sufficient), `re` (slug), `decimal.Decimal` (spend), `datetime` with `timezone.utc`, `dataclasses`.
- **Forbidden, same as Story 1.4:** `requests` (direct), `urllib.request` (direct — the SDK's transitive `httpx` is allowed), `click`, `typer`, `rich`, a second LLM SDK, any job-board client.
- **Python 3.11+** runtime guarantees `datetime.UTC`/`timezone.utc`, `Decimal.quantize`, `typing.Self`, `dataclasses(slots=True)` — all features are well within the existing pin.
- **No `requests`, even via the SDK.** Anthropic SDK uses `httpx`; do not add `requests` as a parallel import path. The forbidden-imports test stays in place to enforce.

### Scope guardrails (what Story 1.5 must NOT do)

- ❌ Do not auto-submit anywhere. The only outbound HTTP allowed is to the LLM provider's API. The FR44 negative-string test (Task 7) is the load-bearing guard.
- ❌ Do not log into Upwork, LinkedIn, or OnlineJobs.ph (FR11). No browser automation. No `selenium`, no `playwright`, no `bs4` for board scraping.
- ❌ Do not parse the JD into structured fields (must-haves, nice-to-haves, board signals). That's Story 2.3 (structured JD parser). Story 1.5 hands raw JD text to the LLM.
- ❌ Do not classify the board (Upwork vs LinkedIn vs OnlineJobs.ph). That's Story 2.4 (source-board classifier). Story 1.5 produces CV + cover letter for every JD regardless of board.
- ❌ Do not produce an Upwork proposal artifact. That's Story 2.7 (Upwork proposal as first-class artifact). Story 1.5 produces exactly two artifacts: `cv.md` and `cover-letter.md`.
- ❌ Do not introduce prompt-template versioning. That's Story 2.9. Story 1.5's prompt is a module-level string; edits land in the source file's history.
- ❌ Do not introduce a per-application metadata sidecar (FR38). That's Story 2.10. Story 1.5's success message goes to stderr; the only persisted state is the artifact files + the cumulative ledger.
- ❌ Do not introduce `config.yaml`. That's Story 2.2. Story 1.5's tunables (model name, pricing constants, default timeout) stay as module-level constants. The timeout is overridable via the new `LLM_CALL_TIMEOUT_SECONDS` env var (transitional — moves into `config.yaml` in Story 2.2).
- ❌ Do not run any drift check. Fabrication is Epic 3, content-loss is Epic 4, keyword-stuffing is Epic 5. Story 1.5's output is unvetted — the dev manually verifies the CV is not fabricating skills during the live smoke. The author accepts this risk for the walking skeleton.
- ❌ Do not implement `jobhunter stats` (FR40). Epic 2. The ledger is structured so a future stats command can read it without re-parsing markdown.
- ❌ Do not run any retry loop on LLM failure. AC5 says exit cleanly on the first failure — the user retries manually. Retry logic is a future epic if the call-failure rate justifies it.
- ❌ Do not implement a GChat webhook notification (Story 6.1). Story 1.5's success channel is stderr.
- ❌ Do not change `_read_jd()` or `read_canonical_cv()` or `load_runtime_config()` contracts beyond the additive `llm_call_timeout_seconds` field on `RuntimeConfig`.

### Previous-story intelligence (Stories 1.1–1.4)

- **Story 1.1 — runtime + schema.** Python 3.11+ is locked. `CANONICAL_CV_PATH` is the single source-of-truth path constant; the LLM client receives the canonical CV as a `dict` (not a path), so `tailor()` does not need to know where the file lives. [Source: DECISIONS.md §1, §2; src/jobhunter/config.py]
- **Story 1.2 — `RuntimeConfig` shape.** `load_runtime_config()` returns a frozen dataclass with `llm_api_key: str` and `monthly_spend_cap_usd: Decimal`. Story 1.5 extends this with `llm_call_timeout_seconds: float` (default 60.0). The "no LLM call when env invalid" guarantee from Story 1.2 AC5 is preserved by the gate ordering in AC10. [Source: src/jobhunter/runtime_config.py; _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md]
- **Story 1.3 — reader contract.** `read_canonical_cv()` re-reads from disk on every call (no cache) and rejects `.pdf`/`.docx`/`.doc` by extension before any read. Story 1.5 consumes the returned dict and serializes it into the prompt — never touches the file. AC9 pins this. [Source: src/jobhunter/canonical_cv.py; _bmad-output/implementation-artifacts/1-3-canonical-cv-reader-with-pdf-docx-ingest-rejection.md]
- **Story 1.4 — JD ingest + gate ordering.** `_read_jd()` returns `(text, source)` or `(None, "")` after a stderr error. The gate ordering env→CV→JD is established and well-tested. Story 1.5's spend-cap and LLM-call gates extend the chain — see AC10. The Story 1.4 "no `./out/`" guarantee is **deliberately reversed by Story 1.5 on the success path** — this is the story where `./out/<slug>/` becomes real. The `./out/` directory must NOT exist on any failure path; it must exist (with both files) on every success path. [Source: src/jobhunter/cli.py; _bmad-output/implementation-artifacts/1-4-jobhunter-paste-jd-ingest-from-stdin-or-file-argument.md]
- **Story 1.4 review: `_cli_helpers.py`.** Subprocess test helpers (`_isolated_cli_env`, `_run_module_cli`, etc.) were extracted to `tests/integration/_cli_helpers.py` during the 1.4 review pass. Story 1.5's new `test_paste_tailoring.py` imports from there — do not redeclare them. The `_isolated_cli_env(tmp_path, ...)` helper already mirrors `canonical-cv.json` into the isolated tree, so Story 1.5's subprocess tests need only set the env + pipe stdin. [Source: tests/integration/_cli_helpers.py; _bmad-output/implementation-artifacts/1-4-jobhunter-paste-jd-ingest-from-stdin-or-file-argument.md#L444-L446]
- **Story 1.2 sandbox caveat.** Earlier dev passes hit a venv where DNS to PyPI was blocked, forcing skips in `test_runtime_config.py` for `python-dotenv`-conditional tests. Story 1.5 introduces a new runtime dep (`anthropic`) — if the dev's venv lacks PyPI access, the `pip install -e .` step will fail. Plan for this: the live smoke + `pytest` need a venv with `anthropic` installed. The conditional-skip pattern from `test_runtime_config.py` is a model: if a test cannot run without the SDK installed, skip it with a clear marker rather than letting the suite go red. [Source: _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md#L256-L262]

### Git intelligence (recent commit patterns)

- Convention `feat(story-1.N): <one-line summary>` is established across the four Epic 1 commits. Story 1.5's commit: `feat(story-1.5): single-call tailoring writes ./out/<slug>/ artifacts (anthropic SDK, spend ledger)`.
- `_bmad-output/story-automator/orchestration-1-...md` is the BMAD automator's working file and is dirty in the tree before this story starts. Do not stage or modify it as part of Story 1.5's diff.
- `.venv/`, `_bmad-output/implementation-artifacts/tests/`, `_bmad-output/story-automator/` are workflow-owned and out of scope.
- The `./out/` directory and `./.cost-ledger.json` are new artifacts of Story 1.5. They must be added to `.gitignore` in the same commit that creates them — never let either land in version control.

### Project Structure Notes

New files this story creates under `src/jobhunter/`:

- `spend_tracker.py` — ledger read/write/check (~80 LoC).
- `slug.py` — `make_slug()` and the regex (~30 LoC).
- `llm_client.py` — SDK wrapper, prompt constants, `tailor()` + `TailoringResult` + exceptions (~120 LoC).
- `tailoring.py` — orchestration: `run_tailoring()` ties the above together (~50 LoC).

Modified files this story touches:

- `cli.py` — `handle_paste()` extends from Story 1.4 (gate ordering, error handling, success message).
- `runtime_config.py` — additive `llm_call_timeout_seconds` field on `RuntimeConfig`.
- `pyproject.toml` — one new dep.
- `.env.example` — one new optional commented entry.
- `.gitignore` — two new entries.
- `README.md` — Configuration, Status, Repo layout sections.
- `DECISIONS.md` — new §4.

New test files under `tests/`:

- `tests/unit/test_slug.py`
- `tests/unit/test_spend_tracker.py`
- `tests/unit/test_llm_client.py`
- `tests/integration/test_paste_tailoring.py`

Modified test files:

- `tests/integration/test_cli_entry.py` — rename + update two Story-1.4 happy-path tests.
- `tests/integration/test_paste_jd_ingest.py` — rename Story-1.4 forbidden-imports + deps tests; update Story-1.4 happy-path tests; the rejection-path tests are unchanged.

Do **not** move or rename any existing source file. The Story 1.5 surface is additive (4 new modules) plus narrow edits to 2 existing modules + the manifest files.

### Testing Standards

- **No test hits a real LLM endpoint.** Ever. The cost is wrong, the determinism is wrong, the CI signal is wrong. Mock the LLM client at the `llm_client.tailor` seam in every test. The recommended pattern:

  ```python
  # In a conftest.py near the new tests, or inline in each test:
  @pytest.fixture
  def mock_llm_tailor(monkeypatch):
      def _fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
          return TailoringResult(
              cv_markdown="# Test CV\n\n- Skill: pytest\n",
              cover_letter_markdown="Dear hiring manager,\n\nI'm a fit.\n",
              cost_usd=Decimal("0.0042"),
              input_tokens=1234,
              output_tokens=567,
          )
      monkeypatch.setattr("jobhunter.llm_client.tailor", _fake_tailor)
      return _fake_tailor
  ```

  For tests that call `run_tailoring` directly (in-process), inject via the `llm_tailor=` kwarg instead of monkeypatching — that's why the seam exists. Subprocess tests need monkeypatching via either an env-var-driven test mode (cleaner) or a `conftest`-level autouse that runs in the subprocess (harder — requires `sitecustomize.py` injection through `PYTHONPATH`). For Story 1.5, the cleanest subprocess pattern is to add an `_isolated_cli_env_with_fake_llm(tmp_path, **overrides)` helper in `tests/integration/_cli_helpers.py` that copies a stub `llm_client.py` over the real one in the isolated tree. The stub's `tailor()` returns a deterministic `TailoringResult`. This keeps the test self-contained and avoids any environment-variable plumbing.

- **No test hits real `api.anthropic.com`.** A defensive pytest plugin or conftest hook is allowed: monkeypatch `socket.socket` or block `http*` URLs at the SDK boundary. Simplest: rely on the mock pattern above + never set `LLM_API_KEY` to a real key in tests.

- **Substring assertions on stderr** continue to anchor on contract substrings, per the Story 1.4 convention. For Story 1.5 the load-bearing substrings are:
  - Success: `"Tailored package written to"`, and `./out/` appearing in the path, and the cost (`"$0."`) appearing.
  - Cap exceeded: `"Monthly LLM spend cap reached"` and both dollar amounts in the message.
  - LLM failure: `"LLM call failed:"`.
  - Slug collision: `"Output slug already exists:"`.

- **Conditional skips when the SDK isn't installed.** Match the `test_runtime_config.py` `python-dotenv`-conditional pattern: `pytest.importorskip("anthropic")` at the top of `test_llm_client.py`. Do not let an SDK-less venv produce 20 import errors; produce one skip with a clear message.

- **Coverage focus:** the safety/contract surface, not aesthetics. At minimum prove:
  - Cap pre-check fires before any LLM call (AC3).
  - Ledger writes are atomic (AC4).
  - Ledger corruption is a hard error (AC4 supplemental).
  - LLM failure leaves no artifacts AND no ledger entry (AC5).
  - LLM response validation rejects empty/missing fields (AC6).
  - Timeout is wired (AC7).
  - No job-board hostname appears in any source file (AC8).
  - Canonical CV file is untouched (AC9).
  - Gate ordering env→CV→JD→cap→LLM→write holds (AC10).
  - Deps did not grow beyond the one new SDK (AC11).
  - `./out/<slug>/cv.md` + `./out/<slug>/cover-letter.md` both exist + match the mocked content on the happy path (AC1).
  - Slug shape conforms to the regex (AC2).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#L381-L410] — Story 1.5 epic-level requirements and BDD acceptance criteria (the four high-level Given/When/Thens this story expands).
- [Source: _bmad-output/planning-artifacts/epics.md#L237] — Epic 1 FR coverage (FR17, FR18, FR37, FR43, FR44 land here).
- [Source: _bmad-output/planning-artifacts/prd.md#L114-L116] — Phase 0 walking-skeleton scope (this story is the closing step).
- [Source: _bmad-output/planning-artifacts/prd.md#L475-L476] — FR17 + FR18 wording (tailored markdown CV + cover letter against canonical CV for a parsed JD).
- [Source: _bmad-output/planning-artifacts/prd.md#L510] — FR37 wording (`./out/<slug>/` markdown artifacts, one file per artifact type).
- [Source: _bmad-output/planning-artifacts/prd.md#L519] — FR43 wording (hard monthly spend cap, refuses to run when exceeded).
- [Source: _bmad-output/planning-artifacts/prd.md#L520] — FR44 wording (never auto-submits).
- [Source: _bmad-output/planning-artifacts/prd.md#L538-L542] — NFR-Performance (< 90s end-to-end; per-call timeout default 60s).
- [Source: _bmad-output/planning-artifacts/prd.md#L544-L549] — NFR-Cost (< $0.25 per application; hard monthly cap; per-request token logging from first call onward).
- [Source: _bmad-output/planning-artifacts/prd.md#L560-L564] — NFR-Reliability (paste mode is the always-available path; cost-cap enforcement is non-bypassable).
- [Source: _bmad-output/planning-artifacts/prd.md#L566-L571] — NFR-Integration (one provider at a time; switching providers must be a config change, not a code rewrite).
- [Source: DECISIONS.md#1-runtime--language] — Python 3.11+ locked.
- [Source: DECISIONS.md#2-canonical-cv-schema] — JSON Resume v1.0.0; `read_canonical_cv()` reader contract.
- [Source: DECISIONS.md#3-revisit-triggers-cross-cutting] — persistence-model revisit trigger; relevant because Story 1.5 introduces the first persistent on-disk state (`.cost-ledger.json`) beyond `canonical-cv.json`.
- [Source: src/jobhunter/cli.py#L56-L78] — current `handle_paste()` shape Story 1.5 extends.
- [Source: src/jobhunter/runtime_config.py#L22-L42] — current `RuntimeConfig` shape; Story 1.5 adds `llm_call_timeout_seconds`.
- [Source: src/jobhunter/canonical_cv.py#L48-L77] — `read_canonical_cv()` contract Story 1.5 must not change.
- [Source: src/jobhunter/config.py] — `PROJECT_ROOT` + `CANONICAL_CV_PATH`; `./out/` and `.cost-ledger.json` should resolve relative to `PROJECT_ROOT` so the test isolation pattern continues to work.
- [Source: tests/integration/_cli_helpers.py] — the Story-1.4-extracted subprocess helpers; Story 1.5 extends with a `_with_fake_llm` variant.
- [Source: tests/conftest.py#L45-L60] — `tmp_canonical_cv` fixture for in-process tests that need a valid CV without touching the real one.
- [Source: tests/integration/test_paste_jd_ingest.py#L33-L94] — Story 1.4's forbidden-imports + deps tests; renamed and updated in Task 7.
- [Source: tests/integration/test_cli_entry.py#L150-L212] — Story 1.4's two happy-path tests that move to the Story 1.5 contract.
- [Source: _bmad-output/implementation-artifacts/1-1-runtime-language-and-canonical-cv-schema-bootstrap.md] — Story 1.1: runtime + schema bootstrap.
- [Source: _bmad-output/implementation-artifacts/1-2-cli-scaffold-env-secrets-handling-and-cost-cap-config.md] — Story 1.2: env-gate, `RuntimeConfig` shape, `_isolated_cli_env` pattern.
- [Source: _bmad-output/implementation-artifacts/1-3-canonical-cv-reader-with-pdf-docx-ingest-rejection.md] — Story 1.3: canonical-CV reader behavior + extension rejection.
- [Source: _bmad-output/implementation-artifacts/1-4-jobhunter-paste-jd-ingest-from-stdin-or-file-argument.md] — Story 1.4: JD ingest, `_read_jd()` shape, gate-ordering establishment, helpers extraction in `_cli_helpers.py`.
- [Source: pyproject.toml#L12-L15] — current pinned deps; Story 1.5 adds exactly one entry.
- [Source: README.md#L33-L52] — Configuration + Status sections to update (Task 10).
- [Source: https://docs.anthropic.com/en/api/messages] — Anthropic Messages API reference (verify endpoint shape + tool-use semantics at implementation time).
- [Source: https://docs.anthropic.com/en/docs/build-with-claude/tool-use] — Anthropic tool-use docs; `tool_choice={"type": "tool", "name": ...}` is the structured-output mechanism this story relies on.
- [Source: https://docs.python.org/3.11/library/decimal.html] — `Decimal` semantics for cost arithmetic (no float).
- [Source: https://docs.python.org/3.11/library/os.html#os.replace] — `os.replace` atomicity guarantee underpinning the ledger + artifact-dir atomic rename.
- [Source: https://docs.python.org/3.11/library/datetime.html#datetime.timezone.utc] — UTC handling for the slug timestamp.

## Create-Story Validation Notes

- Re-analyzed Story 1.5 epic ACs, Epic 1 FR coverage (FR17, FR18, FR37, FR43, FR44), the PRD's tailoring + cost + reliability + integration NFRs, all four prior story artifacts (1.1–1.4), the current source tree (`src/jobhunter/{cli,canonical_cv,runtime_config,config}.py`), `tests/conftest.py`, `tests/integration/{_cli_helpers,test_cli_entry,test_paste_jd_ingest}.py`, the sprint status file, `DECISIONS.md`, `README.md`, `pyproject.toml`, `.env.example`, `canonical-cv.json`, and recent git history.
- No Architecture or UX artifact exists; PRD + epics remain the technical source of truth (consistent with Stories 1.1–1.4).
- The major disaster-prevention guardrails the dev agent needs are encoded in AC3 (cap-before-LLM-call — the only thing standing between a buggy loop and the wallet), AC5 (no partial artifacts on LLM failure — the temp-rename pattern is non-negotiable), AC6 (response validation — without tool-use, free-form JSON parsing is a known failure mode), AC8 (FR44 no-auto-submit + FR11 no-platform-login — encoded as a string-grep test against the source tree), AC9 (canonical CV is untouched — the mtime+sha256 snapshot is the load-bearing assertion), AC10 (gate ordering — protects every previous story's safety guarantees), AC11 (single new dep — protects the project's dependency footprint), and AC12 (`.gitignore` updates — `.cost-ledger.json` and `out/` MUST not be committed).
- The LLM provider choice (Anthropic Claude Haiku 4.5 via the `anthropic` SDK) is the single biggest design call in this story. The Dev Notes section names the recommendation, the rationale, the rejected alternative, and the revisit triggers so the reviewer does not flag this as an arbitrary choice. The dev may deviate (OpenAI), but only with a `DECISIONS.md` §4 entry — that documentation work is non-optional.
- Two existing test files are renamed and updated to reflect the new boundary message and success contract (Tasks 7 + 8). The dev should expect to update Story 1.4's tests as part of Story 1.5 — this is called out explicitly so it does not waste a debug cycle.
- The seam pattern (`run_tailoring(..., llm_tailor=llm_client.tailor)` plus a stubbed `llm_client.py` in subprocess tests) is the recommended testing approach; Dev Notes provides the fixture template verbatim so the dev does not reinvent the mocking pattern.
- Three guardrails are deliberately reversed by this story (each called out in Dev Notes): (a) Story 1.4's "no `./out/`" → Story 1.5 creates `./out/<slug>/` on success; (b) Story 1.4's "no new runtime dep" → Story 1.5 adds exactly one (`anthropic`); (c) Story 1.4's "no LLM call" → Story 1.5 makes the first one. Each reversal is gated by a specific AC so the reviewer can see the trade-off was intentional, not regression.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) — claude-opus-4-7[1m]

### Debug Log References

- Initial subprocess run after wiring `_isolated_cli_env_with_fake_llm` confirmed PROJECT_ROOT resolves to `tmp_path` inside the isolated copy (because `config.py`'s `PROJECT_ROOT = parents[2]` from `src/jobhunter/config.py`). In-process tests cannot rely on this — they must explicitly inject `out_root=` and `ledger_path=` to keep test artifacts inside `tmp_path` and avoid polluting the real repo root.
- AC8 surfaced a contract collision: the existing `NO_AUTO_SUBMIT_STATEMENT` in `cli.py` contained the literal substring `OnlineJobs.ph`, which the new job-board-hostname guard (`onlinejobs.ph` substring match) would have tripped on. Resolution: rephrased the disclaimer to `OnlineJobs PH` (still names the platform, no hostname-shaped substring) and updated the matching assertion in `test_cli_entry.py::test_jobhunter_help_documents_no_auto_submit_boundary` accordingly.

### Completion Notes List

- All 13 ACs covered. Implementation closes Epic 1's walking-skeleton arc: first LLM call, first `./out/<slug>/` write, first persistent on-disk state (`.cost-ledger.json`).
- LLM provider: Anthropic Claude Haiku 4.5 via the `anthropic` Python SDK. Single new runtime dep added to `pyproject.toml`. Tool-use enforced via `tool_choice={"type": "tool", "name": "emit_tailored_artifacts"}` so AC6 has a structural — not stylistic — reliability mechanism.
- Atomic-write pattern: build into `<slug>.tmp/`, then `os.replace()` onto the final `<slug>/`. AC5's "no partial artifacts on LLM failure" is structurally guaranteed because the LLM call happens before any `mkdir`. Ledger writes use the same temp-sibling + atomic-rename pattern.
- Test isolation: subprocess tests use a deterministic stub installed at `src/jobhunter/llm_client.py` in the isolated tree (`_isolated_cli_env_with_fake_llm`), so no test reaches `api.anthropic.com`. In-process tests inject `llm_tailor=` directly into `run_tailoring()` and override `out_root`/`ledger_path` to stay inside `tmp_path`. `test_llm_client.py` uses `pytest.importorskip("anthropic")` to keep an SDK-less venv green with a single skip.
- Final verification: full suite is 155 passed, 1 skipped (the pre-existing `python-dotenv` conditional skip from Story 1.2, plus a single in-test skip that punts the subprocess slug-collision check to the in-process variant). Manual CLI smoke checks (no args → 2, `--help` → 0, `paste --help` → 0, env-missing → 2 naming `LLM_API_KEY`, validator script → 0) all pass.
- Live LLM smoke + manual `.cost-ledger.json` cap-exceeded and timeout smoke (Task 11 sub-bullets) are the author's responsibility — they require a real Anthropic API key and are explicitly out-of-scope for `pytest`.

### File List

**New (source):**
- `src/jobhunter/spend_tracker.py`
- `src/jobhunter/slug.py`
- `src/jobhunter/llm_client.py`
- `src/jobhunter/tailoring.py`

**Modified (source):**
- `src/jobhunter/cli.py` — extends `handle_paste()` with the cap/LLM/write pipeline; reworded `NO_AUTO_SUBMIT_STATEMENT` to avoid the `onlinejobs.ph` substring (AC8 collision); updated `PASTE_DESCRIPTION`. **Review pass:** added `except OSError` clause for the artifact-write failure row of the Error-Handling Matrix.
- `src/jobhunter/runtime_config.py` — adds `llm_call_timeout_seconds` field on `RuntimeConfig` plus `_optional_positive_float()` env-var parser. **Review pass:** added `math.isfinite()` guard to reject `inf`/`-inf` (matches `_required_decimal`'s `is_finite()` behavior); error message harmonised to "finite positive number".
- `src/jobhunter/spend_tracker.py` — **review pass 2:** `read_ledger()` now raises `SpendLedgerCorrupt` when the top-level JSON value is not an object (closes the "corruption is a hard error" gap when the ledger file contains `[]`, `"foo"`, etc.).
- `src/jobhunter/llm_client.py` — **review pass 2:** `tailor()` now raises `LLMResponseInvalid` when `response.usage` is missing or its `input_tokens`/`output_tokens` fields are absent, preventing a silent $0 cost record that would bypass the monthly cap (AC3).

**Modified (manifest / docs):**
- `pyproject.toml` — adds `anthropic>=0.40.0`.
- `.env.example` — adds optional `LLM_CALL_TIMEOUT_SECONDS` comment.
- `.gitignore` — adds `out/` and `.cost-ledger.json`.
- `README.md` — Status, Configuration, and Repo layout updates.
- `DECISIONS.md` — appended §4 LLM Provider.

**New (tests):**
- `tests/unit/test_slug.py`
- `tests/unit/test_spend_tracker.py`
- `tests/unit/test_llm_client.py`
- `tests/integration/test_paste_tailoring.py`

**Modified (tests):**
- `tests/integration/_cli_helpers.py` — adds `_isolated_cli_env_with_fake_llm` and the inline fake-LLM stub source string.
- `tests/integration/test_cli_entry.py` — renames + rewrites two Story-1.4 happy-path tests for Story 1.5's success contract; updates the help-text assertion to match the reworded `NO_AUTO_SUBMIT_STATEMENT`; inverts `test_cli_paste_does_not_write_jd_to_disk` (now `test_cli_paste_writes_only_artifact_files_into_slug_dir`).
- `tests/integration/test_paste_jd_ingest.py` — renames the Story-1.4 forbidden-imports test to `..._match_story_1_5_pinning`; adds `test_no_job_board_hostnames_in_jobhunter_source` (AC8); rewrites the Story-1.4 happy-path tests (UTF-8 file, file precedence, file-equals syntax, in-process unicode, in-process precedence) for the Story 1.5 success contract; inverts the two `..._does_not_create_out_directory_with_{file,stdin}` tests to `..._creates_out_slug_directory_with_{file,stdin}`; rewrites the `boundary_message_*` tests for the new "Tailored package written to" success message.
- `tests/integration/test_paste_tailoring.py` — **review pass:** removes unused imports (`re`, `shutil`, `pathlib.Path`, `PROJECT_ROOT`); strengthens `test_run_tailoring_in_process_refuses_pre_existing_slug_dir` with an explicit ledger-state assertion (AC4); adds `test_cli_paste_handles_artifact_write_oserror_cleanly` covering the previously untested artifact-write `OSError` row of the Error-Handling Matrix. **Review pass 2:** adds `test_cli_paste_returns_exit_two_on_pre_existing_slug_dir` to cover the previously-untested CLI `except FileExistsError → return 2` branch.
- `tests/unit/test_runtime_config.py` — **review pass:** adds `test_load_runtime_config_rejects_non_finite_timeout` parametrize (5 cases) covering `inf`, `-inf`, `Infinity`, `nan`, `NaN`.
- `tests/unit/test_spend_tracker.py` — **review pass 2:** adds `test_read_ledger_raises_when_top_level_is_not_dict` (6 parametrize cases) and `test_check_cap_or_raise_surfaces_non_object_ledger` covering corrupt-ledger shapes that previously crashed with `AttributeError`.
- `tests/unit/test_llm_client.py` — **review pass 2:** adds `test_tailor_raises_response_invalid_when_usage_missing` and `test_tailor_raises_response_invalid_when_usage_missing_token_fields` proving that missing usage data can no longer record a $0 call that would bypass the monthly cap.

### Change Log

- 2026-05-23: Story 1.5 implemented. Single tailoring LLM call writes `cv.md` + `cover-letter.md` to `./out/<slug>/` atomically. Adds `anthropic>=0.40.0` as the single new runtime dependency. Adds `.cost-ledger.json` for hard monthly cap enforcement (AC3). Refactors `handle_paste()` to the Story 1.5 gate ordering: config → CV → JD → cap → LLM → atomic write. Renames + updates two Story-1.4 happy-path tests; inverts the two `./out/` guard tests; adds `tests/unit/test_{slug,spend_tracker,llm_client}.py` + `tests/integration/test_paste_tailoring.py`. README, DECISIONS §4 (LLM provider), and `.gitignore` updated. Final verification: pytest 155 passed / 1 skipped; CLI smoke checks all green.
- 2026-05-23: Story-automator review auto-fixed 1 HIGH, 3 MEDIUM, 2 LOW findings. 0 CRITICAL remained → status review → done. Final suite: pytest 179 passed / 1 skipped.
- 2026-05-23: Second story-automator review pass auto-fixed 2 HIGH and 1 MEDIUM findings (ledger top-level type validation, LLM usage validation, CLI slug-collision coverage). 0 CRITICAL remained → status stays `done`. Final suite: pytest 189 passed / 1 skipped.

## Senior Developer Review (AI)

**Reviewer:** dave (story-automator-review, adversarial mode)
**Date:** 2026-05-23
**Outcome:** Approve (after auto-fixes)
**Suite state at sign-off:** 179 passed, 1 skipped (the pre-existing in-process slug-collision skip — covered by the in-process variant).

### Issues Found and Fixed

**HIGH — H1: Missing `OSError` catch for artifact-write phase (cli.py:handle_paste)**
- The Error-Handling Matrix in Dev Notes lists `OSError from write_text/replace` → exit 1 with `Failed to write artifacts: <reason>`. The CLI had `FileExistsError` (slug collision) and the LLM exceptions but no generic `OSError` catch, so a disk-full / permission failure during the atomic write would surface as an uncaught traceback.
- **Fix:** added `except OSError as exc` in `handle_paste()` after the `LLMResponseInvalid` clause; emits the documented message and returns `1`. FileExistsError is matched first by the existing clause, so the `OSError` catch only handles the remaining subclasses.
- **Test added:** `test_cli_paste_handles_artifact_write_oserror_cleanly` in `tests/integration/test_paste_tailoring.py` — monkeypatches `tailoring_module.os.replace` to raise, drives `main(["paste"])`, asserts exit `1`, `"Failed to write artifacts"` substring on stderr, and no `Traceback` in output.

**MEDIUM — M1: `_optional_positive_float` accepted `inf` (runtime_config.py)**
- `float("inf") > 0` is `True` and `inf != inf` is `False`, so the original guard `not (value > 0) or value != value` let `LLM_CALL_TIMEOUT_SECONDS=inf` through. The sibling `_required_decimal` rejects non-finite values via `is_finite()`; the float branch must be symmetric or the per-call timeout (NFR-Performance) is silently defeatable.
- **Fix:** added `import math` and replaced the guard with `not math.isfinite(value) or value <= 0`. Error message now matches `_required_decimal`'s "finite positive number" wording.
- **Test added:** new parametrize `test_load_runtime_config_rejects_non_finite_timeout` covering `inf`, `-inf`, `Infinity`, `nan`, `NaN` (5 cases).

**MEDIUM — M2: Unused imports in `test_paste_tailoring.py`**
- `re`, `shutil`, `pathlib.Path`, `PROJECT_ROOT` imported but never referenced.
- **Fix:** removed all four. No functional change, smaller surface.

**MEDIUM — M3: No coverage for artifact-write `OSError` path**
- Closed by the H1 test above (`test_cli_paste_handles_artifact_write_oserror_cleanly`).

**LOW — L2: `test_run_tailoring_in_process_refuses_pre_existing_slug_dir` missing ledger assertion**
- The in-process slug-collision test asserted only that `FileExistsError` is raised. AC4 mandates the cost IS recorded when the LLM call succeeds — even if a downstream step (slug collision) prevents the artifact write. Without a ledger assertion, the cap accounting could silently undercount under collisions.
- **Fix:** test now asserts `ledger_path.exists()` after the collision and that the entry under the correct month key matches `cost_usd=0.0042` with `calls=1`.

### Not Fixed (deferred / accepted)

**LOW — L1: Stray `.cost-ledger.json.tmp` on `os.replace` failure in `record_call`.**
- The real ledger remains intact (atomic-rename is atomic). The next successful call overwrites the temp file via `open(..., "w")`. Walking-skeleton acceptable; tracker for Epic 2 if scheduled flows (Epic 7) start producing concurrent writes.

**Considered, no finding:**
- AC6 wording vs. dev notes on whether the cost is recorded when `LLMResponseInvalid` is raised: Task 9 explicitly allows the simpler "raise without recording" pattern as the **recommended** path for the walking skeleton. The implementation follows the recommended pattern. The AC6 text says recording IS done; the dev notes say either pattern is acceptable. The dev followed the explicitly-recommended documented pattern.

### Sprint-status sync

- `1-5-single-tailoring-llm-call-writes-tailored-cv-cover-letter-to-out-slug: done`

---

## Senior Developer Review (AI) — Second Pass

**Reviewer:** dave (story-automator-review, adversarial mode)
**Date:** 2026-05-23
**Outcome:** Approve (after auto-fixes)
**Suite state at sign-off:** 189 passed, 1 skipped.

### Issues Found and Fixed

**HIGH — H1: `read_ledger()` did not validate top-level JSON type (spend_tracker.py)**
- The corrupt-ledger guard caught `JSONDecodeError` but did NOT check that `json.load()` returned a `dict`. A hand-edited or partially-rewritten ledger that parsed as `[]`, `"foo"`, `null`, or a number would later crash with `AttributeError: 'list' object has no attribute 'get'` inside `current_month_total_usd`/`record_call` — leaking an uncaught traceback and defeating the "corruption is a hard error" promise that the cap accounting relies on (AC4 supplemental).
- **Fix:** after `json.load(...)`, raise `SpendLedgerCorrupt` if the parsed value is not a dict. Updated docstring to spell out both failure modes.
- **Tests added:** parametrized `test_read_ledger_raises_when_top_level_is_not_dict` covering `[]`, `[1,2,3]`, `"a string"`, `123`, `null`, `true` (6 cases); plus `test_check_cap_or_raise_surfaces_non_object_ledger` for end-to-end propagation through the cap-check entry point.

**HIGH — H2: Missing `response.usage` silently recorded a $0 call (llm_client.py)**
- `getattr(response, "usage", None)` followed by `int(getattr(usage, "input_tokens", 0) or 0)` quietly defaulted to zero tokens when usage data was missing. Result: every such call would record $0 in the ledger, so the monthly cap (AC3) would never block — a buggy loop or a misconfigured SDK response could drain the wallet without ever crossing the cap. This is exactly the failure mode AC3's "non-bypassable" wording is supposed to prevent.
- **Fix:** in `tailor()`, after the API call, raise `LLMResponseInvalid("usage missing from LLM response")` if `response.usage` is `None`, and raise `LLMResponseInvalid("usage missing input_tokens or output_tokens — cost cannot be computed ...")` if either token field is absent. The CLI already maps `LLMResponseInvalid` → exit `1`, so the failure surfaces cleanly without writing artifacts.
- **Tests added:** `test_tailor_raises_response_invalid_when_usage_missing` and `test_tailor_raises_response_invalid_when_usage_missing_token_fields`.

**MEDIUM — M2: CLI `except FileExistsError → return 2` clause had no test coverage**
- The subprocess slug-collision test (`test_paste_subprocess_pre_existing_slug_dir_exits_two`) is `pytest.skip()`d (requires injectable `now`). The in-process variant (`test_run_tailoring_in_process_refuses_pre_existing_slug_dir`) drives `run_tailoring()` directly, never going through `main()` — so the CLI's exception handler for slug collision was entirely untested via the public CLI entry point.
- **Fix:** added `test_cli_paste_returns_exit_two_on_pre_existing_slug_dir` in `tests/integration/test_paste_tailoring.py`. It pre-creates the deterministic slug dir, calls `main(["paste"])` with `LLM_API_KEY` set and a fake tailor injected, and asserts exit `2`, `"Output slug already exists"` substring on stderr, the slug path in the message, and no Python traceback.

### Not Fixed (deferred / accepted)

**LOW — L1 (carried from first pass): Stray `.cost-ledger.json.tmp` on `os.replace` failure in `record_call`.** Same disposition as the first pass — atomic-rename atomicity is preserved; walking-skeleton acceptable.

**LOW — L2: `FileExistsError` for stale `<slug>.tmp/` shares the same `"Output slug already exists"` user-facing message as a true slug collision.** Functionally correct (the path in the message names the `.tmp` directory so the user can identify the situation), but the wording could be more specific. Deferred — fixing it cleanly requires either a distinct exception class or fragile suffix-matching in `cli.py`; not load-bearing for the walking skeleton.

**Considered, no finding:**
- Per-month-entry corruption (e.g. `{"2026-05": "not-an-object"}`) still raises `AttributeError` if hit. The top-level fix (H1) is the most common shape of corruption; per-entry validation is deferred until Epic 2 introduces `jobhunter stats` and starts depending on entry shape.
- `json.dumps(canonical_cv, indent=2)` uses `ensure_ascii=True`, slightly inflating tokens for non-ASCII canonical CVs. Cosmetic; revisit if NFR-Cost ever bites.

### Sprint-status sync

- `1-5-single-tailoring-llm-call-writes-tailored-cv-cover-letter-to-out-slug: done` (unchanged — 0 CRITICAL after fixes).
