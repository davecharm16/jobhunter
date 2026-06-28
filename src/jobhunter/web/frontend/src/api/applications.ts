export type ApplicationStatus =
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export const STATUS_ORDER: ApplicationStatus[] = [
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export type Application = {
  id: string;
  slug: string | null;
  job_title: string;
  company: string | null;
  url: string | null;
  status: ApplicationStatus;
  notes: string | null;
  cv_markdown: string | null;
  cover_letter_markdown: string | null;
  applied_at: string;
  created_at: string;
  updated_at: string;
};

// Browser-navigable URL for re-downloading a snapshotted artifact.
export function applicationDownloadUrl(
  id: string,
  kind: "cv" | "cover",
): string {
  return `/api/applications/${encodeURIComponent(id)}/download/${kind}`;
}

export async function createApplication(input: {
  slug?: string;
  job_title: string;
  company?: string | null;
  url?: string | null;
}): Promise<Application> {
  const resp = await fetch("/api/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(`createApplication failed: ${resp.status}`);
  return resp.json();
}

export async function updateApplication(
  id: string,
  patch: { status?: ApplicationStatus; notes?: string },
): Promise<Application> {
  const resp = await fetch(`/api/applications/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`updateApplication failed: ${resp.status}`);
  return resp.json();
}

export async function listApplications(
  status?: ApplicationStatus,
): Promise<Application[]> {
  const qs = status ? `?status=${status}` : "";
  const resp = await fetch(`/api/applications${qs}`);
  if (!resp.ok) throw new Error(`listApplications failed: ${resp.status}`);
  return resp.json();
}

// Find the tracked application for a package slug, or null. Used by the
// package page to decide whether to show "I Applied" or the status control.
export async function findApplicationBySlug(
  slug: string,
): Promise<Application | null> {
  const all = await listApplications();
  return all.find((a) => a.slug === slug) ?? null;
}
