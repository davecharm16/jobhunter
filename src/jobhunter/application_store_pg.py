"""Supabase/Postgres-backed ApplicationStore (psycopg v3, synchronous).

Connection string comes from SUPABASE_DB_URL. A connection is opened per
operation (single-user app, low volume) — no pool needed. Status changes and
the matching history row are written in one transaction.
"""

import builtins
import os
import uuid
from typing import Any, Self

import psycopg
from psycopg.rows import dict_row

from jobhunter.application_tracker import (
    INITIAL_STATUS,
    Application,
    StatusChange,
    validate_status,
)

_ISO = "YYYY-MM-DD\"T\"HH24:MI:SS\"Z\""  # render timestamptz as ISO-8601 Z in SQL


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _iso_cols(prefix: str = "") -> str:
    p = f"{prefix}." if prefix else ""
    return (
        f"{p}id::text as id, {p}slug, {p}job_title, {p}company, {p}url, "
        f"{p}status, {p}notes, "
        f"to_char({p}applied_at at time zone 'UTC', '{_ISO}') as applied_at, "
        f"to_char({p}created_at at time zone 'UTC', '{_ISO}') as created_at, "
        f"to_char({p}updated_at at time zone 'UTC', '{_ISO}') as updated_at"
    )


def _row_to_app(row: dict[str, Any]) -> Application:
    return Application(
        id=row["id"],
        slug=row["slug"],
        job_title=row["job_title"],
        company=row["company"],
        url=row["url"],
        status=row["status"],
        notes=row["notes"],
        applied_at=row["applied_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresApplicationStore:
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

    def create(self, *, slug, job_title, company, url) -> Application:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                insert into applications (slug, job_title, company, url, status)
                values (%s, %s, %s, %s, %s)
                returning {_iso_cols()}
                """,
                (slug, job_title, company, url, INITIAL_STATUS),
            ).fetchone()
            assert row is not None
            conn.execute(
                "insert into application_status_history (application_id, from_status, to_status) "
                "values (%s, null, %s)",
                (row["id"], INITIAL_STATUS),
            )
            conn.commit()
            return _row_to_app(row)

    def get(self, app_id) -> Application | None:
        if not _is_uuid(app_id):
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"select {_iso_cols()} from applications where id = %s", (app_id,)
            ).fetchone()
            return _row_to_app(row) if row else None

    def get_by_slug(self, slug) -> Application | None:
        with self._connect() as conn:
            row = conn.execute(
                f"select {_iso_cols()} from applications where slug = %s", (slug,)
            ).fetchone()
            return _row_to_app(row) if row else None

    def list(self, *, status=None) -> builtins.list[Application]:
        with self._connect() as conn:
            if status is not None:
                rows = conn.execute(
                    f"select {_iso_cols()} from applications where status = %s "
                    "order by updated_at desc",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"select {_iso_cols()} from applications order by updated_at desc"
                ).fetchall()
            return [_row_to_app(r) for r in rows]

    def update(self, app_id, *, status=None, notes=None) -> Application | None:
        if not _is_uuid(app_id):
            return None
        with self._connect() as conn:
            current = conn.execute(
                "select status from applications where id = %s", (app_id,)
            ).fetchone()
            if current is None:
                return None
            if status is not None and status != current["status"]:
                validate_status(status)
                conn.execute(
                    "insert into application_status_history (application_id, from_status, to_status) "
                    "values (%s, %s, %s)",
                    (app_id, current["status"], status),
                )
            row = conn.execute(
                f"""
                update applications
                set status = coalesce(%s, status),
                    notes  = coalesce(%s, notes),
                    updated_at = now()
                where id = %s
                returning {_iso_cols()}
                """,
                (status, notes, app_id),
            ).fetchone()
            assert row is not None
            conn.commit()
            return _row_to_app(row)

    def history(self, app_id) -> builtins.list[StatusChange]:
        if not _is_uuid(app_id):
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "select from_status, to_status, "
                f"to_char(changed_at at time zone 'UTC', '{_ISO}') as changed_at "
                "from application_status_history where application_id = %s "
                "order by changed_at asc, id asc",
                (app_id,),
            ).fetchall()
            return [
                StatusChange(
                    from_status=r["from_status"],
                    to_status=r["to_status"],
                    changed_at=r["changed_at"],
                )
                for r in rows
            ]


__all__ = ["PostgresApplicationStore"]
