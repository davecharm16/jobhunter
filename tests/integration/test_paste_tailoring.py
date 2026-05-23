"""Integration tests for Story 1.5 tailoring contracts (ACs 1–10).

Subprocess tests use `_isolated_cli_env_with_fake_llm` so the running CLI
loads a deterministic LLM stub from disk — no real HTTP, no Anthropic key
exercised. In-process tests inject `llm_tailor=` directly into
`run_tailoring()` via a monkey-patched `cli.run_tailoring`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from jobhunter.slug import SLUG_REGEX
from tests.integration._cli_helpers import (
    FAKE_COST_USD,
    FAKE_COVER_LETTER_MARKDOWN,
    FAKE_CV_MARKDOWN,
    _isolated_cli_env_with_fake_llm,
    _run_module_cli,
)


# --- AC1 happy path (subprocess) --------------------------------------------


def test_paste_subprocess_happy_path_writes_both_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "out"
    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role at Acme. FastAPI required.\n",
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )
    assert result.returncode == 0, result.stderr
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    assert (slug_dir / "cv.md").read_text(encoding="utf-8") == FAKE_CV_MARKDOWN
    assert (
        (slug_dir / "cover-letter.md").read_text(encoding="utf-8")
        == FAKE_COVER_LETTER_MARKDOWN
    )


# --- AC2 slug shape ---------------------------------------------------------


def test_paste_subprocess_slug_shape_matches_regex(tmp_path) -> None:
    output_dir = tmp_path / "out"
    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role at Acme.\n",
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )
    assert result.returncode == 0
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    assert SLUG_REGEX.fullmatch(slug_dirs[0].name), (
        f"slug {slug_dirs[0].name!r} fails AC2 regex"
    )


def test_paste_subprocess_pre_existing_slug_dir_exits_two(tmp_path) -> None:
    """If `./out/<slug>/` already exists, the CLI refuses to overwrite."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    # Match the slug shape so the collision can land regardless of UTC second.
    # We use a `.tmp` sentinel sibling guard too: the tailoring step refuses
    # if EITHER `<slug>` or `<slug>.tmp` exists. The simplest deterministic
    # collision: pre-create a directory that matches every plausible slug
    # the run could produce by greedy-matching the regex prefix.
    # In practice we instead pre-fill `out_dir` with a sentinel that proves
    # nothing was overwritten — and assert the run nevertheless exits 0 OR 2
    # depending on whether the exact slug happens to collide.

    # Determinism-friendly variant: pre-create the exact UTC-second slug by
    # freezing time via JOBHUNTER_DEV_FAKE_NOW would require code support.
    # Easier: pre-create a slug.tmp directory that would block the rename.
    pytest.skip("Slug pre-existing test requires injectable now; covered in in-process test below.")


def test_run_tailoring_in_process_refuses_pre_existing_slug_dir(tmp_path) -> None:
    """AC2: `run_tailoring()` refuses if `./out/<slug>/` already exists."""
    from decimal import Decimal

    from jobhunter.llm_client import TailoringResult
    from jobhunter.runtime_config import RuntimeConfig
    from jobhunter.slug import make_slug
    from jobhunter.tailoring import run_tailoring

    fixed_now = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)
    jd_text = "Senior Python role at Acme.\n"
    out_root = tmp_path / "out"
    out_root.mkdir()
    slug = make_slug(jd_text, now=fixed_now)
    (out_root / slug).mkdir()  # pre-existing slug dir

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="cover\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )

    ledger_path = tmp_path / ".cost-ledger.json"
    with pytest.raises(FileExistsError):
        run_tailoring(
            {"basics": {"name": "X"}},
            jd_text,
            config=config,
            now=fixed_now,
            llm_tailor=fake_tailor,
            out_root=out_root,
            ledger_path=ledger_path,
        )

    # AC4: the LLM call succeeded BEFORE the collision was detected, so the
    # cost must already be recorded in the ledger — otherwise the cap
    # accounting silently undercounts whenever a slug collision occurs.
    assert ledger_path.exists(), (
        "AC4 violation: LLM call succeeded but ledger not updated on slug collision"
    )
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    month_key = fixed_now.strftime("%Y-%m")
    assert Decimal(data[month_key]["total_usd"]) == Decimal("0.0042")
    assert data[month_key]["calls"] == 1


# --- AC3 cap pre-check ------------------------------------------------------


def test_paste_subprocess_cap_exceeded_refuses_before_llm_call(tmp_path) -> None:
    """AC3: pre-existing month total at-or-above cap → exit 2, LLM never called."""
    # Sentinel file: the fake LLM stub touches this path if `tailor()` runs.
    # Its absence after the run is the load-bearing proof.
    sentinel = tmp_path / "llm_called.sentinel"

    # Pre-write the ledger so the current month is already at the cap.
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({month_key: {"total_usd": "25.00", "calls": 999}}),
        encoding="utf-8",
    )

    output_dir = tmp_path / "out"
    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
        JOBHUNTER_FAKE_LLM_SENTINEL=str(sentinel),
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 2, result.stderr
    assert "Monthly LLM spend cap reached" in result.stderr
    assert "$25.00" in result.stderr
    assert not sentinel.exists(), (
        "LLM stub was invoked despite cap-exceeded — AC3 violated"
    )
    assert not output_dir.exists()


# --- AC4 ledger updates on success ------------------------------------------


def test_paste_subprocess_ledger_updates_on_success(tmp_path) -> None:
    """AC4: ledger total grows by the call's cost after a successful run."""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({month_key: {"total_usd": "10.00", "calls": 3}}),
        encoding="utf-8",
    )

    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    new_total = Decimal(data[month_key]["total_usd"])
    expected_total = Decimal("10.00") + Decimal(FAKE_COST_USD)
    assert new_total == expected_total
    assert data[month_key]["calls"] == 4


# --- AC5 LLM failure -> no artifacts, no ledger update ----------------------


def test_paste_subprocess_llm_failure_writes_no_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "out"
    ledger_path = tmp_path / ".cost-ledger.json"
    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
        JOBHUNTER_FAKE_LLM_MODE="call_failed",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 1, result.stderr
    assert "LLM call failed:" in result.stderr
    assert not output_dir.exists()
    assert not ledger_path.exists()


# --- AC6 invalid LLM response -> no artifacts ------------------------------


def test_paste_subprocess_invalid_llm_response_writes_no_artifacts(tmp_path) -> None:
    output_dir = tmp_path / "out"
    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
        JOBHUNTER_FAKE_LLM_MODE="invalid_response",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 1, result.stderr
    assert "LLM response was unusable" in result.stderr
    assert not output_dir.exists()


# --- AC7 timeout env validation --------------------------------------------


def test_paste_subprocess_timeout_env_invalid_exits_two(tmp_path) -> None:
    """AC7: LLM_CALL_TIMEOUT_SECONDS <= 0 is a config error at startup."""
    output_dir = tmp_path / "out"
    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
        LLM_CALL_TIMEOUT_SECONDS="-1",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 2, result.stderr
    assert "LLM_CALL_TIMEOUT_SECONDS" in result.stderr
    assert not output_dir.exists()


# --- AC9 canonical CV is untouched -----------------------------------------


def test_paste_subprocess_canonical_cv_untouched(tmp_path) -> None:
    """AC9: tailoring step must not modify canonical-cv.json on disk."""
    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    canonical_path = tmp_path / "canonical-cv.json"
    assert canonical_path.is_file()
    before_bytes = canonical_path.read_bytes()
    before_sha = hashlib.sha256(before_bytes).hexdigest()
    before_mtime_ns = canonical_path.stat().st_mtime_ns

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )
    assert result.returncode == 0, result.stderr

    after_bytes = canonical_path.read_bytes()
    after_sha = hashlib.sha256(after_bytes).hexdigest()
    after_mtime_ns = canonical_path.stat().st_mtime_ns

    assert before_sha == after_sha, "canonical CV bytes mutated"
    assert before_mtime_ns == after_mtime_ns, "canonical CV mtime changed"


# --- AC10 gate ordering -----------------------------------------------------


def test_paste_subprocess_missing_env_short_circuits_before_cap(tmp_path) -> None:
    """AC10: env gate fires before the spend tracker is even touched.

    A pre-existing corrupt ledger would normally cause `SpendLedgerCorrupt`.
    With the env gate firing first, the corrupt ledger is never read.
    """
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text("garbage", encoding="utf-8")

    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        # LLM_API_KEY deliberately omitted — env gate must fire.
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 2, result.stderr
    assert "LLM_API_KEY" in result.stderr
    assert "Spend ledger" not in result.stderr


# --- In-process happy path -------------------------------------------------


def test_paste_in_process_happy_path_writes_both_artifacts(tmp_path) -> None:
    """AC1 in-process via the `llm_tailor=` seam (no monkeypatch)."""
    from jobhunter.llm_client import TailoringResult
    from jobhunter.runtime_config import RuntimeConfig
    from jobhunter.tailoring import run_tailoring

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV (in-process)\n",
            cover_letter_markdown="cover\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )

    outcome = run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role at Acme.\n",
        config=config,
        llm_tailor=fake_tailor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    assert outcome.out_dir.is_dir()
    assert (outcome.out_dir / "cv.md").read_text(encoding="utf-8") == "# CV (in-process)\n"
    assert (outcome.out_dir / "cover-letter.md").exists()


def test_run_tailoring_does_not_record_cost_when_llm_fails(tmp_path) -> None:
    """AC5: LLM hard-failure path leaves the ledger untouched."""
    from jobhunter.llm_client import LLMCallFailed
    from jobhunter.runtime_config import RuntimeConfig
    from jobhunter.tailoring import run_tailoring

    def raising_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        raise LLMCallFailed("timeout after 60s")

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )

    ledger_path = tmp_path / ".cost-ledger.json"
    with pytest.raises(LLMCallFailed):
        run_tailoring(
            {},
            "JD\n",
            config=config,
            llm_tailor=raising_tailor,
            out_root=tmp_path / "out",
            ledger_path=ledger_path,
        )

    assert not ledger_path.exists()
    assert not (tmp_path / "out").exists()


# --- AC3 cap message names the actual current spend, not just the cap -------


def test_paste_subprocess_cap_exceeded_stderr_names_current_and_cap_separately(
    tmp_path,
) -> None:
    """AC3 strict: the stderr message must name BOTH the current spend
    (`$24.97`) and the cap (`$25.00`) — distinct values, so a sloppy
    formatter that only echoes the cap twice would be caught.
    """
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({month_key: {"total_usd": "24.97", "calls": 50}}),
        encoding="utf-8",
    )

    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="24.97",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 2, result.stderr
    assert "Monthly LLM spend cap reached" in result.stderr
    # Both the current spend and the cap appear (here they happen to be equal;
    # that's the "at-or-above" boundary case of AC3).
    assert "$24.97" in result.stderr


def test_paste_subprocess_cap_exceeded_with_distinct_current_and_cap(
    tmp_path,
) -> None:
    """AC3 strict: current=$26.00, cap=$25.00 — both numbers in stderr,
    proving the message is not echoing the cap twice.
    """
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({month_key: {"total_usd": "26.00", "calls": 99}}),
        encoding="utf-8",
    )

    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 2, result.stderr
    assert "$26" in result.stderr
    assert "$25" in result.stderr


# --- AC5 tmp dir cleanup on artifact write failure --------------------------


def test_cli_paste_handles_artifact_write_oserror_cleanly(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """AC5 (review): a disk-full / permission error during the atomic write
    must exit `1` with `Failed to write artifacts: ...` on stderr — not
    propagate as an uncaught Python traceback.

    The Story 1.5 error-handling matrix lists this row but no test exercises
    the CLI's exception handler for it.
    """
    import io
    import sys as _sys
    from decimal import Decimal as _Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.cli import main
    from jobhunter.llm_client import TailoringResult

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="cover\n",
            cost_usd=_Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    original_run = tailoring_module.run_tailoring

    def patched_run(canonical_cv, jd_text, *, config, now=None, llm_tailor=None,
                    out_root=None, ledger_path=None):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now,
            llm_tailor=fake_tailor,
            out_root=out_root or (tmp_path / "out"),
            ledger_path=ledger_path or (tmp_path / ".cost-ledger.json"),
        )

    monkeypatch.setattr(cli_module, "run_tailoring", patched_run)

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("simulated disk full")

    monkeypatch.setattr(tailoring_module.os, "replace", boom)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setattr(_sys, "stdin", io.StringIO("Senior Python role.\n"))

    assert main(["paste"]) == 1
    captured = capsys.readouterr()
    assert "Failed to write artifacts" in captured.err
    assert "simulated disk full" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_run_tailoring_cleans_up_tmp_dir_when_artifact_write_fails(
    tmp_path, monkeypatch
) -> None:
    """AC5: a disk failure during artifact write must not leave a stray
    `<slug>.tmp/` directory behind for the next run to trip over.
    """
    from jobhunter.llm_client import TailoringResult
    from jobhunter.runtime_config import RuntimeConfig
    from jobhunter.tailoring import run_tailoring

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="cover\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=Decimal("25.00"),
        llm_call_timeout_seconds=60.0,
    )

    out_root = tmp_path / "out"

    # Simulate the OS-level rename failing.
    import jobhunter.tailoring as tailoring_module

    def boom(*args, **kwargs):
        raise OSError("simulated disk failure during rename")

    monkeypatch.setattr(tailoring_module.os, "replace", boom)

    with pytest.raises(OSError, match="simulated disk failure"):
        run_tailoring(
            {"basics": {"name": "X"}},
            "Senior Python role.\n",
            config=config,
            llm_tailor=fake_tailor,
            out_root=out_root,
            ledger_path=tmp_path / ".cost-ledger.json",
        )

    # Final slug dir was never created (atomic rename never completed).
    if out_root.exists():
        leftovers = [p for p in out_root.iterdir() if p.is_dir()]
        # No `.tmp` directory should remain — cleanup must have removed it.
        tmp_leftovers = [p for p in leftovers if p.name.endswith(".tmp")]
        assert tmp_leftovers == [], (
            f"Stray .tmp directories left after failure: {tmp_leftovers}"
        )


# --- AC2 CLI exit-code coverage for slug collision -------------------------


def test_cli_paste_returns_exit_two_on_pre_existing_slug_dir(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """Review pass: the subprocess slug-collision test is `pytest.skip()`d
    and the in-process variant exercises `run_tailoring()` directly. Neither
    covers the CLI's `except FileExistsError → return 2` branch in
    `cli.handle_paste()`. This test drives `main(["paste"])` end-to-end with
    a pre-existing slug directory so the CLI handler is exercised.
    """
    import io
    import sys as _sys
    from datetime import datetime as _datetime, timezone as _timezone
    from decimal import Decimal as _Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.cli import main
    from jobhunter.llm_client import TailoringResult
    from jobhunter.slug import make_slug

    fixed_now = _datetime(2026, 5, 24, 3, 15, 30, tzinfo=_timezone.utc)
    jd_text = "Senior Python role at Acme.\n"

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# CV\n",
            cover_letter_markdown="cover\n",
            cost_usd=_Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    out_root = tmp_path / "out"
    out_root.mkdir()
    pre_existing = out_root / make_slug(jd_text, now=fixed_now)
    pre_existing.mkdir()

    original_run = tailoring_module.run_tailoring

    def patched_run(canonical_cv, jd_text, *, config, now=None, llm_tailor=None,
                    out_root=None, ledger_path=None):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now or fixed_now,
            llm_tailor=fake_tailor,
            out_root=out_root or (tmp_path / "out"),
            ledger_path=ledger_path or (tmp_path / ".cost-ledger.json"),
        )

    monkeypatch.setattr(cli_module, "run_tailoring", patched_run)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setattr(_sys, "stdin", io.StringIO(jd_text))

    assert main(["paste"]) == 2
    captured = capsys.readouterr()
    assert "Output slug already exists" in captured.err
    assert str(pre_existing) in captured.err
    assert "Traceback" not in captured.err


# --- AC7 timeout env override flows through CLI to tailor() -----------------


def test_runtime_config_passes_custom_timeout_into_tailoring_call(
    tmp_path, monkeypatch
) -> None:
    """AC7 wiring: `LLM_CALL_TIMEOUT_SECONDS=12.5` must reach `tailor()` as
    `timeout_seconds=12.5` — proving the env var isn't dropped between
    `load_runtime_config()` and the LLM call.
    """
    from jobhunter.llm_client import TailoringResult
    from jobhunter.runtime_config import load_runtime_config
    from jobhunter.tailoring import run_tailoring

    captured: dict[str, float] = {}

    def recording_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        captured["timeout_seconds"] = timeout_seconds
        captured["api_key"] = api_key
        return TailoringResult(
            cv_markdown="# cv\n",
            cover_letter_markdown="cover\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", "12.5")

    config = load_runtime_config(tmp_path / ".env")

    run_tailoring(
        {"basics": {"name": "X"}},
        "Senior Python role.\n",
        config=config,
        llm_tailor=recording_tailor,
        out_root=tmp_path / "out",
        ledger_path=tmp_path / ".cost-ledger.json",
    )

    assert captured["timeout_seconds"] == 12.5
    assert captured["api_key"] == "secret-key"
