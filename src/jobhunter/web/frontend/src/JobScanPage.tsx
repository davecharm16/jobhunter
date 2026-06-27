import { useEffect, useState } from "react";
import {
  listScans, listCandidates, dismissCandidate, generateFromCandidate, runScan,
  SITE_LABEL, type Scan, type Candidate, type Site,
} from "./api/scan";

export function JobScanPage() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [cands, setCands] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const refresh = () => {
    Promise.all([listScans(), listCandidates()])
      .then(([s, c]) => { setScans(s); setCands(c); })
      .finally(() => setLoading(false));
  };
  useEffect(() => { refresh(); }, []);

  const onRun = async () => {
    setRunning(true);
    try {
      await runScan();
      alert("Scan started — new candidates will appear here shortly. Refresh in a moment.");
    } catch (e) {
      alert(`Couldn't start scan: ${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  };

  const RunButton = () => (
    <button
      type="button"
      disabled={running}
      onClick={onRun}
      className="px-4 py-2 bg-primary text-on-primary rounded text-body-md disabled:opacity-50"
    >
      {running ? "Starting…" : "Run scan now (3 per site)"}
    </button>
  );

  const Header = () => (
    <div className="flex items-center justify-between mb-stack-md">
      <h1 className="text-headline-md font-bold">Job Scan</h1>
      <RunButton />
    </div>
  );

  const onGenerate = async (id: string) => {
    setBusy(id);
    try {
      const { slug } = await generateFromCandidate(id);
      window.location.href = `/packages/${slug}`;
    } catch (e) {
      alert(`Generate failed: ${(e as Error).message}`);
      setBusy(null);
    }
  };

  const onDismiss = async (id: string) => {
    try {
      await dismissCandidate(id);
      refresh();
    } catch (e) {
      alert(`Dismiss failed: ${(e as Error).message}`);
    }
  };

  if (loading) {
    return (
      <div className="p-gutter">
        <h1 className="text-headline-md font-bold mb-stack-md">Job Scan</h1>
        <p className="text-on-surface-variant">Loading…</p>
      </div>
    );
  }

  if (scans.length === 0) {
    return (
      <div className="p-gutter">
        <Header />
        <p className="text-on-surface-variant">No scans yet.</p>
      </div>
    );
  }

  return (
    <div className="p-gutter">
      <Header />
      {scans.map((scan) => {
        const scanCands = cands.filter((c) => c.scan_id === scan.id);
        const bySite: Record<string, Candidate[]> = {};
        for (const c of scanCands) (bySite[c.site] ??= []).push(c);
        return (
          <section key={scan.id} className="mb-stack-lg border-b pb-stack-md">
            <div className="flex items-center gap-stack-sm mb-stack-sm">
              <h2 className="text-title-lg font-bold">{new Date(scan.created_at).toLocaleString()}</h2>
              {Object.entries(scan.site_summary).map(([site, info]) => (
                <span key={site} className="text-label-sm px-2 py-0.5 rounded bg-surface-container-high">
                  {SITE_LABEL[site as Site] ?? site}: {info.status} ({info.count})
                </span>
              ))}
            </div>
            {Object.entries(bySite).map(([site, list]) => (
              <div key={site} className="mb-stack-sm">
                <h3 className="text-title-md font-bold mb-1">{SITE_LABEL[site as Site] ?? site}</h3>
                <div className="grid gap-stack-sm">
                  {list.map((c) => (
                    <div key={c.id} className={`border rounded p-3 ${c.status === "dismissed" ? "opacity-50" : ""}`}>
                      <div className="font-bold">{c.title}</div>
                      <div className="text-on-surface-variant text-body-sm">
                        {c.company ?? "—"} · {c.location ?? "—"}
                        {c.fit_score != null && ` · fit ${c.fit_score}`}
                      </div>
                      {c.fit_reason && <div className="text-body-sm mt-1">{c.fit_reason}</div>}
                      <details className="mt-1">
                        <summary className="cursor-pointer text-body-sm">JD preview</summary>
                        <pre className="whitespace-pre-wrap text-body-sm mt-1">{c.jd_text.slice(0, 800)}</pre>
                      </details>
                      <div className="flex gap-stack-sm mt-2">
                        <a href={c.url} target="_blank" rel="noreferrer" className="text-primary underline text-body-sm">
                          Open posting
                        </a>
                        {c.status === "new" && (
                          <>
                            <button disabled={busy === c.id} className="px-3 py-1 bg-primary text-on-primary rounded text-body-sm" onClick={() => onGenerate(c.id)}>
                              {busy === c.id ? "Generating…" : "Generate CV"}
                            </button>
                            <button className="px-3 py-1 border rounded text-body-sm" onClick={() => onDismiss(c.id)}>
                              Dismiss
                            </button>
                          </>
                        )}
                        {c.status === "generated" && c.slug && (
                          <a href={`/packages/${c.slug}`} className="text-primary underline text-body-sm">
                            View package
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
