"""Application-tracker domain types (spec 2026-06-07).

Pure data + the storage interface. No I/O, no SQL, no FastAPI — this module
is import-safe without a database so the route layer can be unit-tested
against an in-memory fake (see tests/fake_application_store.py).
"""

import builtins
from dataclasses import asdict, dataclass
from typing import Protocol

STATUSES: tuple[str, ...] = (
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
)
INITIAL_STATUS = "applied"


def validate_status(status: str) -> None:
    """Raise ValueError if *status* is not a known lifecycle value."""
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r} (allowed: {', '.join(STATUSES)})")


@dataclass
class Application:
    id: str
    slug: str | None
    job_title: str
    company: str | None
    url: str | None
    status: str
    notes: str | None
    applied_at: str
    created_at: str
    updated_at: str
    cv_markdown: str | None = None
    cover_letter_markdown: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StatusChange:
    from_status: str | None
    to_status: str
    changed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class ApplicationStore(Protocol):
    """Storage interface the route layer depends on."""

    def create(
        self,
        *,
        slug: str | None,
        job_title: str,
        company: str | None,
        url: str | None,
        cv_markdown: str | None = None,
        cover_letter_markdown: str | None = None,
    ) -> Application: ...

    def get(self, app_id: str) -> Application | None: ...

    def get_by_slug(self, slug: str) -> Application | None: ...

    def list(self, *, status: str | None = None) -> builtins.list[Application]: ...

    def update(
        self,
        app_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
    ) -> Application | None: ...

    def history(self, app_id: str) -> builtins.list[StatusChange]: ...


__all__ = [
    "STATUSES",
    "INITIAL_STATUS",
    "Application",
    "StatusChange",
    "ApplicationStore",
    "validate_status",
]
