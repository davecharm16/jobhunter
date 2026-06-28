import { useEffect, useState } from "react";
import {
  Application,
  ApplicationStatus,
  STATUS_LABEL,
  STATUS_ORDER,
  createApplication,
  findApplicationBySlug,
  updateApplication,
} from "../api/applications";

type Props = {
  slug: string;
  jobTitle: string;
  company: string | null;
  url: string | null;
  /**
   * "inline" (default) — the compact control used in the header action row.
   * "banner" — a prominent, high-visibility CTA surfaced near the top of the
   * package page so the user can't miss "I Applied" after generating/approving.
   * Both variants share the exact same state + create/update calls (one
   * instance is rendered at a time by the parent — see PackagePage), so there
   * is no duplicated create call or diverging state.
   */
  variant?: "inline" | "banner";
};

export function ApplyControl({
  slug,
  jobTitle,
  company,
  url,
  variant = "inline",
}: Props) {
  const [app, setApp] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    findApplicationBySlug(slug)
      .then((found) => {
        setApp(found);
        setNotes(found?.notes ?? "");
      })
      .finally(() => setLoading(false));
  }, [slug]);

  async function onApply() {
    setBusy(true);
    try {
      const created = await createApplication({
        slug,
        job_title: jobTitle,
        company,
        url,
      });
      setApp(created);
      setNotes(created.notes ?? "");
    } finally {
      setBusy(false);
    }
  }

  async function onStatus(status: ApplicationStatus) {
    if (!app) return;
    setBusy(true);
    try {
      setApp(await updateApplication(app.id, { status }));
    } finally {
      setBusy(false);
    }
  }

  async function onSaveNotes() {
    if (!app) return;
    setBusy(true);
    try {
      setApp(await updateApplication(app.id, { notes }));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return null;

  /* ── Not yet tracked: the "I Applied" call-to-action ──────────────── */
  if (!app) {
    if (variant === "banner") {
      return (
        <div className="rounded-xl border border-primary/40 bg-primary-container/40 p-stack-md shadow-sm flex flex-col gap-stack-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-stack-xs">
            <h2
              className="text-body-lg font-body-lg font-semibold text-on-surface"
              style={{ fontFamily: "var(--font-ui)" }}
            >
              Ready to apply?
            </h2>
            <p className="text-body-md font-body-md text-on-surface-variant">
              Mark this package as applied so the job lands on your applications
              board.
            </p>
          </div>
          <button
            type="button"
            onClick={onApply}
            disabled={busy}
            aria-label="Mark this package as applied and track it"
            className="shrink-0 inline-flex items-center justify-center gap-stack-sm bg-primary text-on-primary text-body-lg font-body-lg font-semibold py-stack-sm px-stack-lg rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
          >
            {busy ? "Tracking..." : "✓ I Applied — track this"}
          </button>
        </div>
      );
    }
    return (
      <button
        type="button"
        onClick={onApply}
        disabled={busy}
        aria-label="Mark this package as applied and track it"
        className="inline-flex items-center gap-stack-sm bg-primary text-on-primary text-body-md font-medium py-stack-sm px-stack-lg rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
      >
        {busy ? "Tracking..." : "✓ I Applied — track this"}
      </button>
    );
  }

  /* ── Already tracked: status + notes management UI (shared) ───────── */
  const manageUI = (
    <div className="flex flex-col gap-stack-sm bg-surface-container-low border border-outline-variant rounded-lg p-stack-md">
      <div className="flex items-center gap-stack-sm">
        <span className="text-label-md text-on-surface-variant">Status</span>
        <select
          value={app.status}
          onChange={(e) => onStatus(e.target.value as ApplicationStatus)}
          disabled={busy}
          className="bg-surface border border-outline-variant rounded-lg px-stack-sm py-stack-xs text-body-md text-on-surface"
        >
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={onSaveNotes}
        placeholder="What to prepare for..."
        className="w-full h-20 bg-surface border border-outline-variant rounded-lg p-stack-sm text-body-md text-on-surface resize-none"
      />
    </div>
  );

  if (variant === "banner") {
    return (
      <div className="rounded-xl border border-primary/40 bg-secondary-container/40 p-stack-md shadow-sm flex flex-col gap-stack-sm">
        <div className="flex flex-wrap items-center gap-stack-sm">
          <span
            className="inline-flex items-center gap-stack-xs text-body-lg font-body-lg font-semibold text-on-surface"
            style={{ fontFamily: "var(--font-ui)" }}
          >
            ✓ Tracked as applied
          </span>
          <span className="inline-flex items-center px-stack-sm py-stack-xs rounded-full border border-outline-variant bg-surface text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
            {STATUS_LABEL[app.status]}
          </span>
        </div>
        {manageUI}
      </div>
    );
  }

  return manageUI;
}
