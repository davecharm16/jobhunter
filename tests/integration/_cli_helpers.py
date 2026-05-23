"""Shared subprocess helpers for `jobhunter` CLI integration tests.

Lives outside the `test_*` discovery prefix so pytest does not collect it as a
test module. Both `test_cli_entry.py` and `test_paste_jd_ingest.py` import the
same primitives from here, so an env-shape change (e.g. adding a new required
env var) lands in one place instead of two.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from jobhunter.config import PROJECT_ROOT


# Deterministic content emitted by the fake-LLM stub installed by
# `_isolated_cli_env_with_fake_llm`. Tests assert on these substrings to
# prove the stub fired and its content reached `./out/<slug>/`.
FAKE_CV_MARKDOWN = "# Tailored CV (test stub)\n\n- Skill: pytest\n"
FAKE_COVER_LETTER_MARKDOWN = (
    "Dear hiring manager,\n\nI am a fit for this role (test stub).\n"
)
FAKE_COST_USD = "0.004200"
FAKE_INPUT_TOKENS = 1234
FAKE_OUTPUT_TOKENS = 567


def _pythonpath_with_src(
    env: dict[str, str],
    src_path: Path | None = None,
) -> dict[str, str]:
    src_path_text = str(PROJECT_ROOT / "src" if src_path is None else src_path)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_path_text
        if not existing_pythonpath
        else os.pathsep.join([src_path_text, existing_pythonpath])
    )
    return env


def _cli_env(src_path: Path | None = None, **overrides: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"LLM_API_KEY", "MONTHLY_SPEND_CAP_USD"}
    }
    env.update(overrides)
    return _pythonpath_with_src(env, src_path)


def _isolated_cli_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    src_path = tmp_path / "src"
    shutil.copytree(
        PROJECT_ROOT / "src" / "jobhunter",
        src_path / "jobhunter",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # Mirror the committed canonical CV into the isolated tree so the Story 1.3
    # reader contract resolves cleanly when env-valid tests reach `read_canonical_cv()`.
    canonical_src = PROJECT_ROOT / "canonical-cv.json"
    if canonical_src.is_file():
        shutil.copyfile(canonical_src, tmp_path / "canonical-cv.json")
    return _cli_env(src_path, **overrides)


_FAKE_LLM_CLIENT_SOURCE = textwrap.dedent(
    f'''\
    """Test-time stub for jobhunter.llm_client.

    Installed into an isolated `src/jobhunter/` tree by
    `_isolated_cli_env_with_fake_llm`. The subprocess-running CLI imports this
    module instead of the real Anthropic-backed one, so no test ever reaches
    `api.anthropic.com`. Set `JOBHUNTER_FAKE_LLM_MODE` to one of:

      - "happy"   (default): return a deterministic TailoringResult.
      - "call_failed": raise LLMCallFailed.
      - "invalid_response": raise LLMResponseInvalid.
      - "sentinel_file:<path>": before returning, touch the sentinel path so
        an external test can detect a real call. Then return the happy result.
    """

    from __future__ import annotations

    import os
    from dataclasses import dataclass
    from decimal import Decimal
    from pathlib import Path
    from typing import Any


    class LLMCallFailed(RuntimeError):
        pass


    class LLMResponseInvalid(RuntimeError):
        pass


    @dataclass(frozen=True)
    class TailoringResult:
        cv_markdown: str
        cover_letter_markdown: str
        cost_usd: Decimal
        input_tokens: int
        output_tokens: int


    FAKE_CV_MARKDOWN = {FAKE_CV_MARKDOWN!r}
    FAKE_COVER_LETTER_MARKDOWN = {FAKE_COVER_LETTER_MARKDOWN!r}
    FAKE_COST_USD = Decimal("{FAKE_COST_USD}")
    FAKE_INPUT_TOKENS = {FAKE_INPUT_TOKENS}
    FAKE_OUTPUT_TOKENS = {FAKE_OUTPUT_TOKENS}


    def tailor(
        canonical_cv: dict[str, Any],
        jd_text: str,
        *,
        api_key: str,
        timeout_seconds: float = 60.0,
    ) -> TailoringResult:
        mode = os.environ.get("JOBHUNTER_FAKE_LLM_MODE", "happy")
        sentinel = os.environ.get("JOBHUNTER_FAKE_LLM_SENTINEL")
        if sentinel:
            Path(sentinel).write_text("called", encoding="utf-8")
        if mode == "call_failed":
            raise LLMCallFailed("provider returned 503")
        if mode == "invalid_response":
            raise LLMResponseInvalid("cv_markdown missing")
        return TailoringResult(
            cv_markdown=FAKE_CV_MARKDOWN,
            cover_letter_markdown=FAKE_COVER_LETTER_MARKDOWN,
            cost_usd=FAKE_COST_USD,
            input_tokens=FAKE_INPUT_TOKENS,
            output_tokens=FAKE_OUTPUT_TOKENS,
        )
    '''
)


def _isolated_cli_env_with_fake_llm(
    tmp_path: Path, **overrides: str
) -> dict[str, str]:
    """Isolated env where `jobhunter.llm_client` is the deterministic stub.

    Subprocess-running tests cannot monkeypatch the imported module in-process,
    so we copy the source tree to tmp_path and overwrite `llm_client.py` with
    a stub that never hits the network. The CLI's `from jobhunter.llm_client
    import LLMCallFailed, LLMResponseInvalid` still resolves cleanly because
    the stub exports both exception classes.
    """
    env = _isolated_cli_env(tmp_path, **overrides)
    src_root = tmp_path / "src" / "jobhunter"
    (src_root / "llm_client.py").write_text(
        _FAKE_LLM_CLIENT_SOURCE, encoding="utf-8"
    )
    return env


def _run_module_cli(
    *args: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jobhunter.cli", *args],
        capture_output=True,
        text=True,
        env=_cli_env() if env is None else env,
        cwd=PROJECT_ROOT if cwd is None else cwd,
        input=input_text,
        timeout=5,
    )
