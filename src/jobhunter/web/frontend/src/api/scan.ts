export type Site = "indeed" | "onlinejobs_ph" | "jobstreet" | "linkedin";
export const SITES: Site[] = ["indeed", "onlinejobs_ph", "jobstreet", "linkedin"];
export const SITE_LABEL: Record<Site, string> = {
  indeed: "Indeed",
  onlinejobs_ph: "OnlineJobs PH",
  jobstreet: "JobStreet",
  linkedin: "LinkedIn",
};

export type ScanSettings = {
  search_titles: string[];
  sites_enabled: Site[];
  picks_per_site: number;
  enabled: boolean;
  location?: string;
  updated_at: string;
};

export type CandidateStatus = "new" | "generated" | "dismissed";

export type Candidate = {
  id: string;
  scan_id: string;
  site: Site;
  url: string;
  title: string;
  company: string | null;
  location: string | null;
  jd_text: string;
  fit_reason: string | null;
  fit_score: number | null;
  status: CandidateStatus;
  slug: string | null;
  created_at: string;
};

export type Scan = {
  id: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  site_summary: Record<string, { status: string; count: number }>;
  created_at: string;
};

async function json<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) throw new Error(`${what} failed: ${resp.status}`);
  return resp.json() as Promise<T>;
}

export async function getScanSettings(): Promise<ScanSettings> {
  return json(await fetch("/api/scan/settings"), "getScanSettings");
}

export async function putScanSettings(s: ScanSettings): Promise<ScanSettings> {
  return json(
    await fetch("/api/scan/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(s),
    }),
    "putScanSettings",
  );
}

export async function listScans(): Promise<Scan[]> {
  return json(await fetch("/api/scan/scans"), "listScans");
}

export async function listCandidates(scanId?: string): Promise<Candidate[]> {
  const q = scanId ? `?scan_id=${encodeURIComponent(scanId)}` : "";
  return json(await fetch(`/api/scan/candidates${q}`), "listCandidates");
}

export async function dismissCandidate(id: string): Promise<Candidate> {
  return json(
    await fetch(`/api/scan/candidates/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "dismissed" }),
    }),
    "dismissCandidate",
  );
}

export async function generateFromCandidate(
  id: string,
): Promise<{ slug: string; status: string }> {
  return json(
    await fetch(`/api/scan/candidates/${encodeURIComponent(id)}/generate`, {
      method: "POST",
    }),
    "generateFromCandidate",
  );
}

// Manually trigger a scan run via the external n8n engine. Surfaces the API's
// detail string on failure (e.g. "scan engine not configured").
export async function runScan(): Promise<{ triggered: boolean }> {
  const resp = await fetch("/api/scan/run", { method: "POST" });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep the status code
    }
    throw new Error(detail);
  }
  return resp.json();
}
