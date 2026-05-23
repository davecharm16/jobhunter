"""Story 6.1 unit tests for `jobhunter.notifier`.

Covers AC2 (payload shape + happy-path POST), AC3 (retry + non-fatal
failure logging), AC4 (human-submits reminder present, no job-board URLs
in the rendered text). httpx network calls are intercepted via a mock
transport so no real HTTP traffic leaves the process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobhunter.metadata import build_metadata, CallLog
from jobhunter.notifier import (
    HUMAN_SUBMITS_REMINDER,
    NotificationPayload,
    NotificationResult,
    build_payload,
    format_message_text,
    notify,
)


FIXED_NOW = datetime(2026, 5, 23, 4, 0, 0, tzinfo=timezone.utc)


def _sample_package_metadata(tmp_path: Path):
    call = CallLog(
        model="claude-haiku-4-5",
        input_tokens=10,
        output_tokens=5,
        usd_cost="0.004200",
        purpose="tailor_cv_and_cover_letter",
    )
    return build_metadata(
        slug="20260523t040000z-senior-python-role",
        jd_source="paste",
        artifacts_produced=["cv", "cover_letter"],
        calls=[call],
        parsed_jd={
            "title": "Senior Python Engineer",
            "must_haves": ["Python", "FastAPI", "Docker"],
        },
        source_board="upwork",
        drift_verdicts={
            "fabrication": "pass",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
        now=FIXED_NOW,
    )


def _make_transport(responses: list[Any]):
    """Build a mock httpx transport that returns *responses* in sequence.

    Each element is either an `httpx.Response` (status + JSON body) or
    an exception instance which is raised to simulate a network error.
    """
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        item = next(iterator)
        if isinstance(item, BaseException):
            raise item
        return item

    return httpx.MockTransport(handler)


# --- AC2: build_payload composes the contracted fields -------------------


def test_build_payload_pulls_fields_from_metadata(tmp_path: Path) -> None:
    md = _sample_package_metadata(tmp_path)
    out_dir = tmp_path / "out" / md.slug
    out_dir.mkdir(parents=True)

    payload = build_payload(md, out_dir)

    assert payload.slug == md.slug
    assert payload.jd_title == "Senior Python Engineer"
    assert payload.source_board == "upwork"
    assert payload.package_path == str(out_dir.resolve())
    assert payload.cost_usd == "0.004200"
    assert payload.file_link == f"file://{out_dir.resolve()}"
    assert "3 must-haves matched" in payload.fit_summary


def test_build_payload_falls_back_to_slug_when_title_missing(
    tmp_path: Path,
) -> None:
    md = build_metadata(
        slug="20260523t040000z-anonymous",
        jd_source="paste",
        artifacts_produced=["cv"],
        calls=[],
        parsed_jd={"must_haves": []},
        source_board="other",
        drift_verdicts={
            "fabrication": "pass",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
        now=FIXED_NOW,
    )
    out_dir = tmp_path / md.slug
    out_dir.mkdir()

    payload = build_payload(md, out_dir)

    assert payload.jd_title == "20260523t040000z-anonymous"


# --- AC4: message text includes the reminder, no job-board URLs ----------


def test_format_message_text_contains_human_submits_reminder(
    tmp_path: Path,
) -> None:
    md = _sample_package_metadata(tmp_path)
    out_dir = tmp_path / md.slug
    out_dir.mkdir()
    payload = build_payload(md, out_dir)

    text = format_message_text(payload)

    assert HUMAN_SUBMITS_REMINDER in text


def test_format_message_text_excludes_job_board_urls(tmp_path: Path) -> None:
    """AC4: the rendered text must not contain any submission URL."""
    md = _sample_package_metadata(tmp_path)
    out_dir = tmp_path / md.slug
    out_dir.mkdir()
    payload = build_payload(md, out_dir)

    text = format_message_text(payload).lower()
    # Two layers: literal hostnames must not appear, and the explicit
    # word "submit" (as opposed to the reminder phrase) must not point
    # at any URL scheme other than `file://`.
    for hostname in (
        "upwork." + "com",
        "linkedin." + "com",
        "onlinejobs." + "ph",
    ):
        assert hostname not in text
    # The only URL scheme we emit is `file://` — no `http(s)://` slips
    # through unless someone wires a board URL into the payload.
    assert "https://" not in text
    assert "http://" not in text


def test_format_message_text_includes_required_fields(tmp_path: Path) -> None:
    md = _sample_package_metadata(tmp_path)
    out_dir = tmp_path / md.slug
    out_dir.mkdir()
    payload = build_payload(md, out_dir)

    text = format_message_text(payload)

    assert "Senior Python Engineer" in text
    assert "upwork" in text
    assert "0.004200" in text
    assert f"file://{out_dir.resolve()}" in text


# --- AC2: happy-path delivery returns delivered=True ---------------------


def _payload() -> NotificationPayload:
    return NotificationPayload(
        slug="slug",
        jd_title="JD",
        source_board="other",
        package_path="/tmp/p",
        cost_usd="0.004200",
        file_link="file:///tmp/p",
        fit_summary="JD — other — 1 must-have matched",
    )


def test_notify_returns_delivered_on_2xx(monkeypatch) -> None:
    transport = _make_transport(
        [httpx.Response(200, json={"ok": True})]
    )

    # Patch httpx.Client so it uses our MockTransport.
    real_client = httpx.Client

    def _client_with_transport(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("jobhunter.notifier.httpx.Client", _client_with_transport)

    result = notify(_payload(), webhook_url="https://example.test/hook", sleep=_no_sleep)

    assert result == NotificationResult(
        delivered=True, attempts=1, last_status=200, last_error=None
    )


def test_notify_retries_5xx_then_succeeds(monkeypatch) -> None:
    transport = _make_transport(
        [
            httpx.Response(502, json={"err": "bad gateway"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    _patch_client(monkeypatch, transport)
    sleeps: list[float] = []

    result = notify(
        _payload(),
        webhook_url="https://example.test/hook",
        sleep=sleeps.append,
    )

    assert result.delivered is True
    assert result.attempts == 2
    assert result.last_status == 200
    # Exponential backoff: first failure -> 1s sleep before retry.
    assert sleeps == [1.0]


def test_notify_returns_delivery_failed_after_retries_exhausted(
    monkeypatch, capsys
) -> None:
    """AC3: 3 attempts on 5xx, all fail, returns delivered=False + stderr log."""
    transport = _make_transport(
        [
            httpx.Response(502),
            httpx.Response(503),
            httpx.Response(500),
        ]
    )
    _patch_client(monkeypatch, transport)
    sleeps: list[float] = []

    result = notify(
        _payload(),
        webhook_url="https://example.test/hook",
        sleep=sleeps.append,
    )

    assert result.delivered is False
    assert result.attempts == 3
    assert result.last_status == 500
    assert result.last_error == "http_500"
    # Two sleeps between three attempts: 1s, then 2s.
    assert sleeps == [1.0, 2.0]
    captured = capsys.readouterr()
    assert "GChat notification failed after 3 attempts" in captured.err
    assert "/tmp/p" in captured.err  # package_path surfaced in stderr


def test_notify_does_not_retry_4xx(monkeypatch, capsys) -> None:
    """AC3: 4xx is terminal — no retries, single attempt, delivery_failed."""
    transport = _make_transport([httpx.Response(403)])
    _patch_client(monkeypatch, transport)
    sleeps: list[float] = []

    result = notify(
        _payload(),
        webhook_url="https://example.test/hook",
        sleep=sleeps.append,
    )

    assert result.delivered is False
    assert result.attempts == 1
    assert result.last_status == 403
    assert result.last_error == "http_403"
    assert sleeps == []
    captured = capsys.readouterr()
    assert "after 1 attempts" in captured.err


def test_notify_retries_network_error(monkeypatch, capsys) -> None:
    """AC3: an httpx.HTTPError (timeout, DNS, etc) triggers a retry."""
    transport = _make_transport(
        [
            httpx.ConnectError("DNS failure"),
            httpx.ConnectError("DNS failure"),
            httpx.ConnectError("DNS failure"),
        ]
    )
    _patch_client(monkeypatch, transport)
    sleeps: list[float] = []

    result = notify(
        _payload(),
        webhook_url="https://example.test/hook",
        sleep=sleeps.append,
    )

    assert result.delivered is False
    assert result.attempts == 3
    assert result.last_status is None
    assert "ConnectError" in (result.last_error or "")
    assert sleeps == [1.0, 2.0]
    captured = capsys.readouterr()
    assert "GChat notification failed after 3 attempts" in captured.err


def test_notify_posts_json_body_with_text_field(monkeypatch) -> None:
    """AC2: body is JSON with a `text` field that includes the reminder."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = _json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    _patch_client(monkeypatch, transport)

    result = notify(
        _payload(),
        webhook_url="https://example.test/hook",
        sleep=_no_sleep,
    )

    assert result.delivered is True
    assert captured["url"] == "https://example.test/hook"
    assert "text" in captured["body"]
    assert HUMAN_SUBMITS_REMINDER in captured["body"]["text"]
    # Structured payload rides alongside the rendered text.
    assert captured["body"]["payload"]["slug"] == "slug"


# --- Helpers --------------------------------------------------------------


def _no_sleep(_: float) -> None:
    return None


def _patch_client(monkeypatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.Client

    def _client_with_transport(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("jobhunter.notifier.httpx.Client", _client_with_transport)
