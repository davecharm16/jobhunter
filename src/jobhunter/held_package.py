"""Held-package writer + retention sweep (Story 3.4).

When the Story 3.2 fabrication matcher emits `verdict: "fail"`, the package
enters the HELD state: tailored markdown stays on disk, a `package.held.json`
sidecar is written next to the existing artifacts, and the per-application
metadata gets `held: true` + `held_path: <path>` so a future `GET /api/queue`
(Epic 6, FR35) can list held packages without re-parsing drift reports.

Two contracts live in this module:

1. `compose_held_record` + `write_held_sidecar` — pure functions the
   orchestrator calls after `write_drift_report`. The composer pins each
   failed claim to a precise `(artifact_path, line_number, column_start,
   column_end)` location so the author can jump straight to it in their
   editor (AC1).

2. `sweep_expired` — invoked at the TOP of `run_tailoring` before any LLM
   work. Walks `./out/` for `package.held.json` sidecars whose
   `retention_expires_at` is in the past and removes the whole `<slug>/`
   directory; appends a one-line JSON-lines audit entry per discard to
   `./out/_discarded.log` (Story 3.4 AC3, file renamed by Story 6.5 AC3).
   Story 6.5 AC3 also extends the per-discard entry shape with
   `source_board`, `drift_fail_reason`, and `created_at` read from the
   slug's `metadata.json` sibling. A `retention_days=0` call short-circuits
   to a no-op (Story 6.5 AC1: `0` disables auto-discard).

The "no notify" contract (AC2) is structural — this module does not import
or reference any notification module, and `tailoring.py`'s held branch goes
through this module only. Notifications land in Epic 6.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from jobhunter.content_loss_matcher import DroppedEntry
from jobhunter.fabrication_matcher import UnsourcedClaim
from jobhunter.keyword_stuffing_matcher import KeywordStuffingCheck
from jobhunter.metadata import now_iso8601_utc


_log = logging.getLogger(__name__)


__all__ = [
    "AUDIT_LOG_NAME",
    "HELD_SIDECAR_NAME",
    "DroppedHighImpactEntry",
    "FailedClaim",
    "HeldPackageRecord",
    "KeywordStuffingViolation",
    "compose_held_record",
    "iter_dropped_high_impact_entries",
    "iter_keyword_stuffing_violations",
    "sweep_expired",
    "write_held_sidecar",
]


HELD_SIDECAR_NAME = "package.held.json"
# Story 6.5 AC3: rename the per-discard audit log from `_held-audit.log`
# (Story 3.4's name) to `_discarded.log` (the spec's literal name).
AUDIT_LOG_NAME = "_discarded.log"

# Maps `source_artifact` (from `UnsourcedClaim`) to the on-disk markdown
# filename the failed claim lives in. Mirrors the
# `_CLAIM_EXTRACTION_SOURCES` table in `tailoring.py`.
_SOURCE_ARTIFACT_FILENAMES: dict[str, str] = {
    "cv": "cv.md",
    "cover_letter": "cover-letter.md",
    "upwork_proposal": "upwork-proposal.md",
}


@dataclass(frozen=True)
class FailedClaim:
    """One failed claim pinned to a precise location in a tailored artifact."""

    claim_id: str
    claim_text: str
    source_artifact: str
    line_number: int
    reason: str
    artifact_path: str
    column_start: int
    column_end: int


@dataclass(frozen=True)
class DroppedHighImpactEntry:
    """One high-impact canonical-CV entry dropped from every tailored artifact (Story 4.2 AC6).

    Mirrors `content_loss_matcher.DroppedEntry` but lives on `package.held.json`
    so a future `GET /api/queue` can enumerate content-loss holds without
    re-parsing `package.drift.json`. The `reason` field is the same enumerated
    set as the drift report (`silently_lost` is the fail-discriminating value).
    """

    entry_id: str
    section: str
    primary_text: str
    jd_requirements_addressed: list[str]
    reason: str


@dataclass(frozen=True)
class KeywordStuffingViolation:
    """One keyword-stuffing violation projected onto the held sidecar (Story 5.3 AC4).

    Flattens Stories 5.1's `DensityViolation` and Story 5.2's dump-paragraph /
    comma-run location dicts into a uniform per-violation shape so a future
    `GET /api/queue` can enumerate keyword-stuffing holds without re-parsing
    `package.drift.json`. `kind` discriminates the three sources:

    - `density_violation` — Story 5.1 per-keyword density / repetition breach.
    - `keyword_dump_paragraph` — Story 5.2 dump-paragraph hit.
    - `comma_run_violation` — Story 5.2 comma-run hit.

    Fields that don't apply to a given kind are empty / zero (e.g. a density
    violation has no `paragraph_index`). Mirrors `DroppedHighImpactEntry`'s
    structural pattern: one frozen dataclass, all fields populated for every
    record so the on-disk shape stays diff-stable.
    """

    kind: Literal[
        "density_violation", "keyword_dump_paragraph", "comma_run_violation"
    ]
    artifact: str
    keyword: str = ""
    paragraph_index: int = -1
    occurrences: int = 0
    total_tokens: int = 0
    density_pct: float = 0.0
    keyword_ratio: float = 0.0
    threshold_breached: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    excerpt: str = ""


@dataclass(frozen=True)
class HeldPackageRecord:
    """`package.held.json` payload (AC1 field list, verbatim).

    Story 4.2 AC6 adds `dropped_high_impact_entries` (additive, defaults to
    `[]`) so a content-loss-only fail can write a held sidecar without a
    `failed_claims[]` entry — and a combined fabrication + content-loss fail
    populates both lists. Story 5.3 AC4 adds `keyword_stuffing_violations`
    (additive, defaults to `[]`) following the same idiom: a keyword-stuffing
    fail flattens its density + placement violations into this list. The
    `held_by_check` field stays `"fabrication"` for backward compatibility
    with Story 3.4's tests; the on-disk presence of a non-empty
    `dropped_high_impact_entries[]` or `keyword_stuffing_violations[]` is the
    structural marker that the corresponding check contributed to the verdict.
    """

    held_at: str
    held_by_check: Literal["fabrication"]
    failed_claims: list[FailedClaim] = field(default_factory=list)
    retention_expires_at: str = ""
    recoverable: bool = True
    dropped_high_impact_entries: list[DroppedHighImpactEntry] = field(
        default_factory=list
    )
    keyword_stuffing_violations: list[KeywordStuffingViolation] = field(
        default_factory=list
    )


def compose_held_record(
    unsourced_claims: list[UnsourcedClaim],
    out_dir: Path,
    *,
    now: datetime,
    retention_days: int,
    dropped_entries: list[DroppedEntry] | None = None,
    keyword_stuffing_check: KeywordStuffingCheck | None = None,
) -> HeldPackageRecord:
    """Build a `HeldPackageRecord` from the matcher's unsourced claims.

    Each `FailedClaim` carries the precise `column_start`/`column_end`
    offsets of the claim text within its source-artifact markdown line, so
    an editor integration (or the author manually) can jump straight to the
    fabricated text. When the claim text cannot be located on the recorded
    line a WARNING is logged and a `(0, len(claim_text))` span is used.

    Story 4.2 AC6: when *dropped_entries* is supplied (the content-loss
    matcher's `silently_lost` drops), each one is projected into a
    `DroppedHighImpactEntry` and stored under `dropped_high_impact_entries`.

    Story 5.3 AC4: when *keyword_stuffing_check* is supplied AND its verdict
    is `"fail"`, its density violations + placement locations are projected
    into `KeywordStuffingViolation` records and stored under
    `keyword_stuffing_violations`. A `pass` verdict (or `None`) leaves the
    list empty, mirroring the additive idiom of `dropped_entries`. Both
    arguments are keyword-only with `None` defaults so Story 3.4/4.2 callers
    stay source-compatible.
    """
    held_at_dt = _ensure_utc(now)
    retention_dt = held_at_dt + timedelta(days=retention_days)
    failed_claims = [
        _build_failed_claim(claim, out_dir) for claim in unsourced_claims
    ]
    dropped_high_impact = list(iter_dropped_high_impact_entries(dropped_entries or []))
    keyword_stuffing_violations = list(
        iter_keyword_stuffing_violations(keyword_stuffing_check)
    )
    return HeldPackageRecord(
        held_at=now_iso8601_utc(held_at_dt),
        held_by_check="fabrication",
        failed_claims=failed_claims,
        retention_expires_at=now_iso8601_utc(retention_dt),
        recoverable=True,
        dropped_high_impact_entries=dropped_high_impact,
        keyword_stuffing_violations=keyword_stuffing_violations,
    )


def iter_dropped_high_impact_entries(
    dropped_entries: list[DroppedEntry],
) -> list[DroppedHighImpactEntry]:
    """Project content-loss `DroppedEntry`s into the held-sidecar shape (Story 4.2 AC6).

    Only `silently_lost` drops contribute to the held state — `irrelevant_to_jd`
    drops carry a logged rationale and do not fail the check (Story 4.1 AC3 +
    Story 4.2 AC2), so they must not appear on `package.held.json` either or
    the held sidecar would mis-report the fail-cause to a future
    `GET /api/queue`.
    """
    return [
        DroppedHighImpactEntry(
            entry_id=entry.entry_id,
            section=entry.section,
            primary_text=entry.primary_text,
            jd_requirements_addressed=list(entry.jd_requirements_addressed),
            reason=entry.reason,
        )
        for entry in dropped_entries
        if entry.reason == "silently_lost"
    ]


def iter_keyword_stuffing_violations(
    check: KeywordStuffingCheck | None,
) -> list[KeywordStuffingViolation]:
    """Project a `KeywordStuffingCheck` into the held-sidecar shape (Story 5.3 AC4).

    Only contributes records when *check* is non-None AND verdict=="fail":
    a passing check (or `None`) leaves the field empty so a fabrication-only
    or content-loss-only fail stays diff-stable against Story 3.4/4.2's
    fixtures. Density violations and placement locations are flattened into
    a single `KeywordStuffingViolation` list discriminated by `kind`.
    """
    if check is None or check.verdict != "fail":
        return []
    violations: list[KeywordStuffingViolation] = []
    for density in check.density_violations:
        violations.append(
            KeywordStuffingViolation(
                kind="density_violation",
                artifact=density.artifact,
                keyword=density.keyword,
                occurrences=density.occurrences,
                total_tokens=density.total_tokens,
                density_pct=density.density_pct,
                threshold_breached=density.threshold_breached,
            )
        )
    for location in check.dump_paragraph_locations:
        kind = location.get("kind", "")
        if kind not in ("keyword_dump_paragraph", "comma_run_violation"):
            continue
        violations.append(
            KeywordStuffingViolation(
                kind=kind,  # type: ignore[arg-type]
                artifact=str(location.get("artifact", "")),
                paragraph_index=int(location.get("paragraph_index", -1)),
                keyword_ratio=float(location.get("keyword_ratio", 0.0)),
                matched_keywords=list(location.get("matched_keywords", [])),
                excerpt=str(location.get("excerpt", "")),
            )
        )
    return violations


def write_held_sidecar(out_dir: Path, record: HeldPackageRecord) -> Path:
    """Write `package.held.json` atomically into *out_dir* and return its path."""
    target = out_dir / HELD_SIDECAR_NAME
    tmp_path = out_dir / ".package.held.tmp"
    payload = asdict(record)
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, target)
    return target


def sweep_expired(
    out_root: Path,
    *,
    now: datetime,
    retention_days: int,
) -> list[str]:
    """Discard every held package under *out_root* whose retention has expired.

    Scans `out_root` for `<slug>/package.held.json` sidecars; for each whose
    `retention_expires_at` is in the past relative to *now*, removes the
    entire `<slug>/` directory and appends a one-line JSON record to
    `out_root/_discarded.log` so the discard is not silent. Returns the
    list of discarded slugs.

    Story 6.5 AC1: `retention_days == 0` short-circuits to a no-op (auto-
    discard disabled). The check sits AT THE TOP — before `out_root.is_dir`
    even — because the contract is "the sweep does nothing", regardless of
    whether the queue directory exists.

    Story 6.5 AC3: the audit entry is extended with `source_board`,
    `drift_fail_reason`, and `created_at` read from the slug's
    `metadata.json` (best-effort; absent/malformed metadata yields empty
    strings rather than aborting the discard).

    Story 6.5 AC4: only directories with a `package.held.json` sidecar are
    eligible — passed packages (no sidecar) and overridden packages (under
    `out_root/_overridden/<slug>/`, never iterated because we walk
    `out_root` non-recursively) are structurally excluded.

    Best-effort: any per-slug failure (unreadable sidecar, permission error
    on rmtree) is logged at WARNING and the sweep continues with the next
    slug — the sweep must never abort the pipeline.
    """
    if retention_days == 0:
        return []
    if not out_root.is_dir():
        return []

    moment = _ensure_utc(now)
    discarded: list[str] = []
    for entry in sorted(out_root.iterdir()):
        if not entry.is_dir():
            continue
        sidecar = entry / HELD_SIDECAR_NAME
        if not sidecar.is_file():
            continue
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _log.warning(
                "held-package sweep: could not read %s: %s", sidecar, exc
            )
            continue
        expires_raw = payload.get("retention_expires_at")
        if not isinstance(expires_raw, str):
            _log.warning(
                "held-package sweep: %s missing retention_expires_at", sidecar
            )
            continue
        try:
            expires_at = _parse_iso8601(expires_raw)
        except ValueError as exc:
            _log.warning(
                "held-package sweep: %s has malformed retention_expires_at: %s",
                sidecar,
                exc,
            )
            continue
        if expires_at > moment:
            continue
        held_at_raw = payload.get("held_at")
        failed_claims = payload.get("failed_claims") or []
        failed_count = len(failed_claims) if isinstance(failed_claims, list) else 0
        # Story 6.5 AC3: pull the new audit fields from `metadata.json` BEFORE
        # the rmtree wipes the directory. Best-effort: a missing or malformed
        # metadata.json yields empty-string fields so the discard still
        # proceeds and the audit entry still lands.
        metadata_fields = _read_metadata_audit_fields(entry)
        slug = entry.name
        try:
            shutil.rmtree(entry)
        except OSError as exc:
            _log.warning(
                "held-package sweep: could not remove %s: %s", entry, exc
            )
            continue
        _append_audit_entry(
            out_root,
            slug=slug,
            held_at=held_at_raw if isinstance(held_at_raw, str) else "",
            discarded_at=now_iso8601_utc(moment),
            failed_claims_count=failed_count,
            source_board=metadata_fields["source_board"],
            drift_fail_reason=metadata_fields["drift_fail_reason"],
            created_at=metadata_fields["created_at"],
        )
        discarded.append(slug)
    return discarded


def _read_metadata_audit_fields(slug_dir: Path) -> dict[str, str]:
    """Read `metadata.json` and project Story 6.5 AC3's audit fields.

    Returns a dict with three string keys: `source_board`,
    `drift_fail_reason`, `created_at`. Missing / malformed metadata.json or
    missing individual fields yield empty strings — the sweep never aborts
    on a metadata read failure.

    `drift_fail_reason` is derived from `metadata.drift_verdicts`: the
    sorted, comma-joined list of check names whose verdict is `"fail"`
    (e.g. `"fabrication"`, `"content_loss,fabrication"`). When no check
    failed (unexpected for a held package, but possible if the sidecar was
    written without updating metadata) the field is the empty string.
    """
    empty = {"source_board": "", "drift_fail_reason": "", "created_at": ""}
    metadata_path = slug_dir / "metadata.json"
    if not metadata_path.is_file():
        return empty
    try:
        doc = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning(
            "held-package sweep: could not read %s: %s", metadata_path, exc
        )
        return empty
    if not isinstance(doc, dict):
        return empty
    source_board = doc.get("source_board", "")
    created_at = doc.get("created_at", "")
    drift_verdicts = doc.get("drift_verdicts") or {}
    failing: list[str] = []
    if isinstance(drift_verdicts, dict):
        failing = sorted(
            check
            for check, verdict in drift_verdicts.items()
            if isinstance(check, str) and verdict == "fail"
        )
    return {
        "source_board": source_board if isinstance(source_board, str) else "",
        "drift_fail_reason": ",".join(failing),
        "created_at": created_at if isinstance(created_at, str) else "",
    }


def _build_failed_claim(claim: UnsourcedClaim, out_dir: Path) -> FailedClaim:
    """Materialise one `FailedClaim` with editor-precise column offsets."""
    filename = _SOURCE_ARTIFACT_FILENAMES.get(
        claim.source_artifact, f"{claim.source_artifact}.md"
    )
    artifact_path = out_dir / filename
    column_start, column_end = _locate_claim_columns(
        artifact_path=artifact_path,
        line_number=claim.line_number,
        claim_text=claim.claim_text,
    )
    return FailedClaim(
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        source_artifact=claim.source_artifact,
        line_number=claim.line_number,
        reason=claim.reason,
        artifact_path=str(artifact_path),
        column_start=column_start,
        column_end=column_end,
    )


def _locate_claim_columns(
    *,
    artifact_path: Path,
    line_number: int,
    claim_text: str,
) -> tuple[int, int]:
    """Find the first occurrence of *claim_text* on *line_number* of *artifact_path*.

    Falls back to `(0, len(claim_text))` and logs a WARNING when the file
    cannot be read, the line is out of range, or the claim text is not
    present on that line. Line numbers are 1-indexed (matching the Story 3.1
    `Claim.line_number` contract); column offsets are 0-indexed characters
    within the line, exclusive of the trailing newline.
    """
    try:
        text = artifact_path.read_text(encoding="utf-8")
    except OSError as exc:
        _log.warning(
            "held-package writer: could not read %s for column offsets: %s",
            artifact_path,
            exc,
        )
        return (0, len(claim_text))
    lines = text.splitlines()
    if line_number < 1 or line_number > len(lines):
        _log.warning(
            "held-package writer: line %d out of range in %s (have %d lines)",
            line_number,
            artifact_path,
            len(lines),
        )
        return (0, len(claim_text))
    line_text = lines[line_number - 1]
    column_start = line_text.find(claim_text)
    if column_start < 0:
        _log.warning(
            "held-package writer: claim %r not found on line %d of %s",
            claim_text,
            line_number,
            artifact_path,
        )
        return (0, len(claim_text))
    return (column_start, column_start + len(claim_text))


def _append_audit_entry(
    out_root: Path,
    *,
    slug: str,
    held_at: str,
    discarded_at: str,
    failed_claims_count: int,
    source_board: str = "",
    drift_fail_reason: str = "",
    created_at: str = "",
) -> None:
    """Append one JSON-lines record to `out_root/_discarded.log`.

    Story 6.5 AC3 extends the entry shape with three fields read from the
    discarded slug's `metadata.json`: `source_board`, `drift_fail_reason`
    (sorted comma-joined check names whose drift verdict was `"fail"`), and
    `created_at`. All three default to empty strings so callers that supply
    no metadata still produce a structurally-stable record.
    """
    entry = {
        "slug": slug,
        "held_at": held_at,
        "discarded_at": discarded_at,
        "failed_claims_count": failed_claims_count,
        "source_board": source_board,
        "drift_fail_reason": drift_fail_reason,
        "created_at": created_at,
    }
    log_path = out_root / AUDIT_LOG_NAME
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=False) + "\n")


def _ensure_utc(moment: datetime) -> datetime:
    """Normalise a naive or aware datetime to UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _parse_iso8601(value: str) -> datetime:
    """Parse an ISO 8601 timestamp with a trailing `Z` (the `now_iso8601_utc` shape)."""
    # `fromisoformat` accepts `+00:00` but not the literal `Z` until 3.11; the
    # repo targets 3.13 where `Z` parses directly. Normalising here keeps the
    # function tolerant of either form.
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
