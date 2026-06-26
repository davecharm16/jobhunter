"""Google Chat webhook notification on pass (Story 6.1).

Contract (Story 6.2 pins this structurally): pass -> notify on GChat; fail
-> hold quietly under ./out/<slug>/ (identified by metadata.held=true +
package.held.json + drift-report.md sidecars), no notification. Story 6.2
locks the contract via tests + the call-graph gate in `tailoring.py`, which
checks `held_path_value is None AND _all_drift_pass(drift_verdicts)` before
any call into this module — a failing drift verdict structurally cannot
reach the webhook.

Architectural deviation from the original Story 6.2 spec wording: held
packages are co-located at `./out/<slug>/` rather than under a separate
`./out/_held/<slug>/` tree. Stories 3.4 / 4.2 / 5.3 shipped that working
architecture; the `held=true` flag on `metadata.json` plus the
`package.held.json` and `drift-report.md` sidecars are the structural
markers for the HELD state. Story 6.2 keeps that contract intact.

The notification is fire-and-forget from the pipeline's perspective: any
delivery failure is logged and the metadata sidecar's `notification` field
captures the outcome, but the pipeline still exits cleanly because the
package itself succeeded.

Transport: synchronous `httpx.Client` POST with explicit timeout. httpx is
already available transitively via `fastapi[all]` (Story 1.6) so this
module does NOT add a direct dependency — `tests/unit/test_secret_hygiene`
forbids `httpx` / `requests` / `selenium` / `playwright` in pyproject.

Retry policy (AC3): exponential backoff (1s, 2s, 4s) on 5xx responses and
network errors, up to *retries* attempts total. 4xx responses are terminal
(no retry — the webhook URL is wrong or the payload is rejected).

Message-body rules (AC4):
- MUST include the explicit human-submits reminder so the operator sees a
  review-and-submit instruction in-chat.
- MUST NOT contain any job-board hostname (the integration test
  `test_no_job_board_hostnames_in_jobhunter_source` pins this FR44/FR11
  contract repo-wide). The package path is exposed as a local `file://`
  link; the tool never auto-submits.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from jobhunter.metadata import PackageMetadata


__all__ = [
    "HUMAN_SUBMITS_REMINDER",
    "NotificationPayload",
    "NotificationResult",
    "build_payload",
    "build_scan_message",
    "format_message_text",
    "notify",
    "notify_scan",
]


_log = logging.getLogger(__name__)

# AC4: this exact string must appear in every outbound message so the human
# operator sees a review-and-submit reminder in GChat.
HUMAN_SUBMITS_REMINDER = "Ready for your review — submit when satisfied"

_DEFAULT_TIMEOUT_SECONDS: float = 10.0
_BACKOFF_BASE_SECONDS: float = 1.0


@dataclass(frozen=True)
class NotificationPayload:
    """The shape of the GChat message body (AC2)."""

    slug: str
    jd_title: str
    source_board: str
    package_path: str
    cost_usd: str
    file_link: str
    fit_summary: str


@dataclass(frozen=True)
class NotificationResult:
    """Outcome of a `notify(...)` call; folded into metadata.notification."""

    delivered: bool
    attempts: int
    last_status: int | None
    last_error: str | None


def build_payload(
    package_metadata: PackageMetadata, out_dir: Path
) -> NotificationPayload:
    """Compose the GChat payload from the staged metadata sidecar."""
    slug = package_metadata.slug
    parsed_jd = package_metadata.parsed_jd or {}
    jd_title = parsed_jd.get("title") or slug
    source_board = package_metadata.source_board
    package_path = str(out_dir.resolve())
    cost_usd = package_metadata.cost.total_usd
    file_link = f"file://{package_path}"
    fit_summary = _format_fit_summary(jd_title, source_board, parsed_jd)
    return NotificationPayload(
        slug=slug,
        jd_title=jd_title,
        source_board=source_board,
        package_path=package_path,
        cost_usd=cost_usd,
        file_link=file_link,
        fit_summary=fit_summary,
    )


def format_message_text(payload: NotificationPayload) -> str:
    """Render the GChat `text` field — what the user actually reads in-chat.

    Single string with the fit summary on the first line, then a compact
    "key: value" block (board, title, cost, path) and the human-submits
    reminder on the last line. AC4 forbids any job-board URL anywhere in
    this text — the package link is a `file://` local pointer only.
    """
    return (
        f"{payload.fit_summary}\n"
        f"Board: {payload.source_board}\n"
        f"Role: {payload.jd_title}\n"
        f"Cost: ${payload.cost_usd}\n"
        f"Package: {payload.file_link}\n"
        f"{HUMAN_SUBMITS_REMINDER}"
    )


def notify(
    payload: NotificationPayload,
    *,
    webhook_url: str,
    retries: int = 3,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    sleep: Any = time.sleep,
) -> NotificationResult:
    """POST *payload* to GChat with exponential-backoff retries (AC2 + AC3).

    `retries` is the total attempt budget — `retries=3` means up to three
    POSTs separated by 1s and 2s sleeps (the third attempt's failure-side
    4s sleep is skipped because there is no fourth attempt). 4xx responses
    are terminal and consume one attempt. The body is the JSON
    `{"text": format_message_text(payload), "payload": <asdict(payload)>}`
    so both human-readable rendering and structured fields ride together
    over the same POST.
    """
    body = {
        "text": format_message_text(payload),
        "payload": asdict(payload),
    }
    last_status: int | None = None
    last_error: str | None = None
    attempts = 0
    with httpx.Client(timeout=timeout_seconds) as client:
        for attempt in range(1, retries + 1):
            attempts = attempt
            try:
                response = client.post(webhook_url, json=body)
            except httpx.HTTPError as exc:
                last_status = None
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                    continue
                break

            last_status = response.status_code
            if 200 <= response.status_code < 300:
                return NotificationResult(
                    delivered=True,
                    attempts=attempts,
                    last_status=last_status,
                    last_error=None,
                )
            if 400 <= response.status_code < 500:
                last_error = f"http_{response.status_code}"
                break
            last_error = f"http_{response.status_code}"
            if attempt < retries:
                sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                continue

    print(
        (
            f"jobhunter: GChat notification failed after {attempts} attempts "
            f"({last_error}) — package at {payload.package_path} is on disk"
        ),
        file=sys.stderr,
    )
    return NotificationResult(
        delivered=False,
        attempts=attempts,
        last_status=last_status,
        last_error=last_error,
    )


def build_scan_message(
    *, new_count: int, site_summary: dict[str, Any], dashboard_url: str
) -> str:
    """Discovery notification. Dashboard link only — NEVER job-board hostnames
    (FR44/FR11; test_no_job_board_hostnames_in_jobhunter_source)."""
    parts = [
        f"🔎 Job Scan: {new_count} new candidate{'s' if new_count != 1 else ''}."
    ]
    for site, info in sorted(site_summary.items()):
        status = info.get("status", "?")
        count = info.get("count", 0)
        parts.append(f"• {site}: {status} ({count})")
    parts.append(f"Review on your dashboard: {dashboard_url}")
    return "\n".join(parts)


def notify_scan(webhook_url: str, message: str, *, retries: int = 3) -> None:
    """Fire-and-forget POST to GChat. Failures are logged, never raised."""
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(webhook_url, json={"text": message})
    except Exception as exc:  # noqa: BLE001 - non-fatal by contract
        logging.getLogger(__name__).warning("scan notification failed: %s", exc)


def _format_fit_summary(
    jd_title: str, source_board: str, parsed_jd: dict
) -> str:
    """One-line scannable summary the operator reads first in-chat."""
    must_haves = parsed_jd.get("must_haves")
    if isinstance(must_haves, list) and must_haves:
        count = len(must_haves)
        noun = "must-have" if count == 1 else "must-haves"
        return f"{jd_title} — {source_board} — {count} {noun} matched"
    return f"{jd_title} — {source_board} — ready for review"
