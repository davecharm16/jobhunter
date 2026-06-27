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
};

export function ApplyControl({ slug, jobTitle, company, url }: Props) {
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

  if (!app) {
    return (
      <button
        type="button"
        onClick={onApply}
        disabled={busy}
        className="bg-primary text-on-primary text-body-md font-medium py-stack-sm px-stack-lg rounded-lg hover:bg-primary-container disabled:opacity-50 transition-colors"
      >
        {busy ? "Tracking..." : "I Applied"}
      </button>
    );
  }

  return (
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
}
