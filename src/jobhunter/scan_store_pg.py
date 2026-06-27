"""Supabase/Postgres ScanStore (psycopg v3, sync). Connection per op."""

from __future__ import annotations

import builtins
import os
import uuid
from typing import Any, Self

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from jobhunter.scan import (
    Candidate,
    CandidateInput,
    Scan,
    ScanSettings,
    validate_candidate_status,
)

_ISO = "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\""


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _ts(col: str, alias: str) -> str:
    return f"to_char({col} at time zone 'UTC', '{_ISO}') as {alias}"


class PostgresScanStore:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    @classmethod
    def from_env(cls) -> Self:
        db_url = os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            raise RuntimeError("SUPABASE_DB_URL is not set")
        return cls(db_url)

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    # ---- settings ----
    def get_settings(self) -> ScanSettings:
        with self._connect() as conn:
            row = conn.execute(
                f"select search_titles, sites_enabled, picks_per_site, enabled, "
                f"{_ts('updated_at','updated_at')} from scan_settings where id = true"
            ).fetchone()
            assert row is not None
            return _row_to_settings(row)

    def update_settings(self, *, search_titles, sites_enabled, picks_per_site,
                        enabled) -> ScanSettings:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                update scan_settings
                set search_titles = %s, sites_enabled = %s,
                    picks_per_site = %s, enabled = %s, updated_at = now()
                where id = true
                returning search_titles, sites_enabled, picks_per_site, enabled,
                          {_ts('updated_at','updated_at')}
                """,
                (list(search_titles), list(sites_enabled), picks_per_site, enabled),
            ).fetchone()
            assert row is not None
            conn.commit()
            return _row_to_settings(row)

    # ---- scans / candidates ----
    def known_urls(self) -> builtins.list[str]:
        with self._connect() as conn:
            rows = conn.execute("select url from scan_candidates").fetchall()
            return [r["url"] for r in rows]

    def record_scan(self, *, started_at, finished_at, status, site_summary,
                    candidates: builtins.list[CandidateInput]) -> tuple[Scan, int, int]:
        with self._connect() as conn:
            scan_row = conn.execute(
                f"""
                insert into scans (started_at, finished_at, status, site_summary)
                values (%s, %s, %s, %s)
                returning id::text as id,
                          {_ts('started_at','started_at')},
                          {_ts('finished_at','finished_at')},
                          status, site_summary,
                          {_ts('created_at','created_at')}
                """,
                (started_at, finished_at, status, Jsonb(site_summary)),
            ).fetchone()
            assert scan_row is not None
            scan_id = scan_row["id"]
            new = skipped = 0
            for ci in candidates:
                inserted = conn.execute(
                    """
                    insert into scan_candidates
                        (scan_id, site, url, title, company, location, jd_text,
                         fit_reason, fit_score)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (url) do nothing
                    returning id
                    """,
                    (scan_id, ci.site, ci.url, ci.title, ci.company, ci.location,
                     ci.jd_text, ci.fit_reason, ci.fit_score),
                ).fetchone()
                if inserted is None:
                    skipped += 1
                else:
                    new += 1
            conn.commit()
            return _row_to_scan(scan_row), new, skipped

    def list_candidates(self, *, status=None, scan_id=None) -> builtins.list[Candidate]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        if scan_id is not None:
            if not _is_uuid(scan_id):
                return []
            clauses.append("scan_id = %s")
            params.append(scan_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"select {_cand_cols()} from scan_candidates {where} "
                "order by created_at desc, id asc",
                tuple(params),
            ).fetchall()
            return [_row_to_cand(r) for r in rows]

    def get_candidate(self, candidate_id) -> Candidate | None:
        if not _is_uuid(candidate_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"select {_cand_cols()} from scan_candidates where id = %s",
                (candidate_id,),
            ).fetchone()
            return _row_to_cand(row) if row else None

    def set_candidate_status(self, candidate_id, *, status, slug=None) -> Candidate | None:
        validate_candidate_status(status)
        if not _is_uuid(candidate_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"""
                update scan_candidates
                set status = %s, slug = coalesce(%s, slug)
                where id = %s
                returning {_cand_cols()}
                """,
                (status, slug, candidate_id),
            ).fetchone()
            if row is None:
                return None
            conn.commit()
            return _row_to_cand(row)

    def list_scans(self) -> builtins.list[Scan]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select id::text as id,
                       {_ts('started_at','started_at')},
                       {_ts('finished_at','finished_at')},
                       status, site_summary,
                       {_ts('created_at','created_at')}
                from scans order by created_at desc
                """
            ).fetchall()
            return [_row_to_scan(r) for r in rows]


def _cand_cols() -> str:
    return (
        "id::text as id, scan_id::text as scan_id, site, url, title, company, "
        "location, jd_text, fit_reason, fit_score, status, slug, "
        + _ts("created_at", "created_at")
    )


def _row_to_settings(row: dict[str, Any]) -> ScanSettings:
    return ScanSettings(
        search_titles=list(row["search_titles"]),
        sites_enabled=list(row["sites_enabled"]),
        picks_per_site=row["picks_per_site"],
        enabled=row["enabled"],
        updated_at=row["updated_at"],
    )


def _row_to_scan(row: dict[str, Any]) -> Scan:
    return Scan(
        id=row["id"], started_at=row["started_at"], finished_at=row["finished_at"],
        status=row["status"], site_summary=row["site_summary"],
        created_at=row["created_at"],
    )


def _row_to_cand(row: dict[str, Any]) -> Candidate:
    return Candidate(
        id=row["id"], scan_id=row["scan_id"], site=row["site"], url=row["url"],
        title=row["title"], company=row["company"], location=row["location"],
        jd_text=row["jd_text"], fit_reason=row["fit_reason"],
        fit_score=float(row["fit_score"]) if row["fit_score"] is not None else None,
        status=row["status"], slug=row["slug"], created_at=row["created_at"],
    )


__all__ = ["PostgresScanStore"]
