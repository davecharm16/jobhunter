"""In-memory ApplicationStore for fast, DB-free tests.

Importable as `tests.fake_application_store` because pyproject sets
pythonpath = ["src", "."].
"""

from __future__ import annotations

import itertools

from jobhunter.application_tracker import (
    INITIAL_STATUS,
    Application,
    StatusChange,
    validate_status,
)

_FIXED_TS = "2026-06-07T00:00:00Z"


class FakeApplicationStore:
    def __init__(self) -> None:
        self._apps: dict[str, Application] = {}
        self._history: dict[str, list[StatusChange]] = {}
        self._ids = (f"app-{n}" for n in itertools.count(1))

    def create(
        self,
        *,
        slug,
        job_title,
        company,
        url,
        cv_markdown=None,
        cover_letter_markdown=None,
    ) -> Application:
        app_id = next(self._ids)
        app = Application(
            id=app_id,
            slug=slug,
            job_title=job_title,
            company=company,
            url=url,
            status=INITIAL_STATUS,
            notes=None,
            applied_at=_FIXED_TS,
            created_at=_FIXED_TS,
            updated_at=_FIXED_TS,
            cv_markdown=cv_markdown,
            cover_letter_markdown=cover_letter_markdown,
        )
        self._apps[app_id] = app
        self._history[app_id] = [
            StatusChange(from_status=None, to_status=INITIAL_STATUS, changed_at=_FIXED_TS)
        ]
        return app

    def get(self, app_id) -> Application | None:
        return self._apps.get(app_id)

    def get_by_slug(self, slug) -> Application | None:
        for app in self._apps.values():
            if app.slug == slug:
                return app
        return None

    def list(self, *, status=None) -> list[Application]:
        apps = list(self._apps.values())
        if status is not None:
            apps = [a for a in apps if a.status == status]
        return sorted(apps, key=lambda a: a.updated_at, reverse=True)

    def update(self, app_id, *, status=None, notes=None) -> Application | None:
        app = self._apps.get(app_id)
        if app is None:
            return None
        if status is not None and status != app.status:
            validate_status(status)
            self._history[app_id].append(
                StatusChange(from_status=app.status, to_status=status, changed_at=_FIXED_TS)
            )
            app.status = status
        if notes is not None:
            app.notes = notes
        app.updated_at = _FIXED_TS
        return app

    def history(self, app_id) -> list[StatusChange]:
        return list(self._history.get(app_id, []))
