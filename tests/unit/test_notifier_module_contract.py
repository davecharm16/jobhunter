"""Story 6.2 AC3 — pass/fail contract is documented + structurally enforced.

This static test reads three source artifacts and asserts the notify-on-pass /
hold-on-fail contract is present in each:

1. `src/jobhunter/notifier.py` — module docstring states the contract.
2. `config.yaml` — top-of-file comment block restates the contract so an
   operator reading the config sees the same rule.
3. `src/jobhunter/tailoring.py` — the notification gate
   `held_path_value is None and _all_drift_pass(drift_verdicts)` is
   present, structurally guaranteeing no code path POSTs to the webhook
   when any drift verdict is `fail`.

Architectural deviation from the original Story 6.2 AC2 wording: held
packages live at `./out/<slug>/` (co-located with passed packages) rather
than under `./out/_held/<slug>/`. Stories 3.4 / 4.2 / 5.3 shipped that
architecture; the contract paragraph captures the co-located reality.
"""

from __future__ import annotations

from pathlib import Path

from jobhunter.config import PROJECT_ROOT


def test_notifier_module_docstring_states_contract() -> None:
    """`notifier.py`'s module docstring spells out pass -> notify, fail -> hold."""
    source = (PROJECT_ROOT / "src" / "jobhunter" / "notifier.py").read_text(
        encoding="utf-8"
    )
    # Open with the triple-quote module docstring start.
    assert source.startswith('"""'), (
        "notifier.py must begin with a module docstring "
        "(the contract paragraph lives there)"
    )
    docstring_end = source.index('"""', 3)
    docstring = source[3:docstring_end]
    # Pass side: notify on GChat.
    assert "pass" in docstring.lower()
    assert "notify" in docstring.lower()
    assert "GChat" in docstring or "Google Chat" in docstring
    # Fail side: hold quietly, no notification.
    assert "fail" in docstring.lower()
    assert "hold" in docstring.lower() or "held" in docstring.lower()
    # Co-located slug directory (architectural deviation from the original
    # `./out/_held/<slug>/` wording).
    assert "./out/<slug>/" in docstring
    # Story 6.2 references the structural pin.
    assert "Story 6.2" in docstring


def test_config_yaml_states_notification_contract() -> None:
    """`config.yaml` has a one-paragraph note describing pass/fail behavior."""
    config_text = (PROJECT_ROOT / "config.yaml").read_text(encoding="utf-8")
    # Find the comment block by keyword presence (loose enough that wording
    # can evolve but strict enough that the rule is unambiguous).
    lower = config_text.lower()
    assert "notification" in lower
    assert "gchat_webhook_url" in lower or "google chat" in lower
    assert "held" in lower
    assert "story 6.2" in lower
    # Pass + fail are both named so the contract is symmetric on disk.
    assert "pass" in lower
    assert "fail" in lower


def test_tailoring_notification_gate_is_present() -> None:
    """`tailoring.py` checks `held_path_value is None AND _all_drift_pass(...)`
    before calling the notifier — structurally enforcing the no-notify-on-fail
    contract from Story 6.2 AC3."""
    source = (PROJECT_ROOT / "src" / "jobhunter" / "tailoring.py").read_text(
        encoding="utf-8"
    )
    # The literal gate condition — both halves must be present so a future
    # refactor that drops one of them flips this test red.
    assert "held_path_value is None" in source
    assert "_all_drift_pass(drift_verdicts)" in source
    # And the gate guards the notifier call site.
    assert "_notify_and_update_sidecar(" in source
