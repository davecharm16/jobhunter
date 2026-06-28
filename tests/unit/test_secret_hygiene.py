"""Repository-level tests for local secret hygiene and submit guardrails."""

from __future__ import annotations

from jobhunter.config import PROJECT_ROOT


def test_gitignore_excludes_dotenv_files_but_allows_example() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore


def test_env_example_contains_only_placeholders() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "LLM_API_KEY=replace-with-your-provider-key" in env_example
    assert "MONTHLY_SPEND_CAP_USD=25.00" in env_example
    assert "sk-" not in env_example
    assert "api_key_here" not in env_example.lower()


def test_no_job_board_submit_dependencies_or_source_paths() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    forbidden_dependencies = ["requests", "httpx", "selenium", "playwright"]
    for dependency in forbidden_dependencies:
        assert dependency not in pyproject

    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "src").rglob("*.py")
    ).lower()

    assert "submit_application" not in source_text
    assert "apply_to_job" not in source_text
    assert "api.upwork" not in source_text
    assert "linkedin.com/jobs" not in source_text
    assert "onlinejobs.ph/jobseekers" not in source_text
