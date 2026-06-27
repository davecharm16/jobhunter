import { useEffect, useMemo, useState } from "react";
import {
  listScans, listCandidates, dismissCandidate, generateFromCandidate, runScan,
  SITES, SITE_LABEL, type Scan, type Candidate, type Site,
} from "./api/scan";

type Tab = "all" | Site;

export function JobScanPage() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [cands, setCands] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  // filters
  const [tab, setTab] = useState<Tab>("all");
  const [query, setQuery] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [sortByFit, setSortByFit] = useState(true);

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

  // count per site honoring the show-dismissed toggle (for tab badges)
  const counts = useMemo(() => {
    const base = cands.filter((c) => showDismissed || c.status !== "dismissed");
    const m: Record<string, number> = { all: base.length };
    for (const s of SITES) m[s] = base.filter((c) => c.site === s).length;
    return m;
  }, [cands, showDismissed]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = cands
      .filter((c) => tab === "all" || c.site === tab)
      .filter((c) => showDismissed || c.status !== "dismissed")
      .filter((c) =>
        !q ||
        c.title.toLowerCase().includes(q) ||
        (c.company ?? "").toLowerCase().includes(q),
      );
    if (sortByFit) {
      list = [...list].sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0));
    }
    return list;
  }, [cands, tab, query, showDismissed, sortByFit]);

  const latestScan = scans[0];

  if (loading) {
    return (
      <div className="p-gutter">
        <h1 className="text-headline-md font-bold mb-stack-md">Job Scan</h1>
        <p className="text-on-surface-variant">Loading…</p>
      </div>
    );
  }

  return (
    <div className="p-gutter">
      {/* header */}
      <div className="flex items-center justify-between mb-stack-md">
        <h1 className="text-headline-md font-bold">Job Scan</h1>
        <button
          type="button"
          disabled={running}
          onClick={onRun}
          className="px-4 py-2 bg-primary text-on-primary rounded text-body-md disabled:opacity-50"
        >
          {running ? "Starting…" : "Run scan now"}
        </button>
      </div>

      {/* latest-scan per-site status chips */}
      {latestScan && (
        <div className="flex flex-wrap items-center gap-stack-sm mb-stack-sm text-label-sm text-on-surface-variant">
          <span>Last scan {new Date(latestScan.created_at).toLocaleString()}:</span>
          {Object.entries(latestScan.site_summary).map(([site, info]) => (
            <span key={site} className="px-2 py-0.5 rounded bg-surface-container-high">
              {SITE_LABEL[site as Site] ?? site}: {info.status} ({info.count})
            </span>
          ))}
        </div>
      )}

      {/* tabs by site */}
      <div className="flex flex-wrap gap-stack-xs border-b border-outline-variant mb-stack-sm">
        {(["all", ...SITES] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={
              "px-3 py-2 text-body-md border-b-2 -mb-px " +
              (tab === t
                ? "border-primary text-primary font-bold"
                : "border-transparent text-on-surface-variant hover:text-on-surface")
            }
          >
            {t === "all" ? "All" : SITE_LABEL[t as Site]} ({counts[t] ?? 0})
          </button>
        ))}
      </div>

      {/* filters */}
      <div className="flex flex-wrap items-center gap-stack-md mb-stack-md text-body-sm">
        <input
          type="text"
          placeholder="Search title / company…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="border border-outline-variant rounded px-2 py-1 bg-surface-container-lowest min-w-[220px]"
        />
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={sortByFit} onChange={(e) => setSortByFit(e.target.checked)} />
          Sort by fit
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
          Show dismissed
        </label>
        <span className="text-on-surface-variant">{visible.length} shown</span>
      </div>

      {/* cards */}
      {visible.length === 0 ? (
        <p className="text-on-surface-variant">No candidates match — try another tab or run a scan.</p>
      ) : (
        <div className="grid gap-stack-sm">
          {visible.map((c) => (
            <div
              key={c.id}
              className={`border border-outline-variant rounded-lg p-3 ${c.status === "dismissed" ? "opacity-50" : ""}`}
            >
              <div className="flex items-center gap-stack-sm">
                <span className="text-label-sm px-2 py-0.5 rounded bg-surface-container-high">
                  {SITE_LABEL[c.site] ?? c.site}
                </span>
                <span className="font-bold">{c.title}</span>
                {c.fit_score != null && (
                  <span className="text-label-sm text-primary">fit {c.fit_score}</span>
                )}
                {c.status === "generated" && (
                  <span className="text-label-sm text-on-surface-variant">· generated</span>
                )}
              </div>
              <div className="text-on-surface-variant text-body-sm mt-1">
                {c.company ?? "—"} · {c.location ?? "—"}
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
                    <button
                      disabled={busy === c.id}
                      className="px-3 py-1 bg-primary text-on-primary rounded text-body-sm disabled:opacity-50"
                      onClick={() => onGenerate(c.id)}
                    >
                      {busy === c.id ? "Generating…" : "Generate CV"}
                    </button>
                    <button className="px-3 py-1 border border-outline-variant rounded text-body-sm" onClick={() => onDismiss(c.id)}>
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
      )}
    </div>
  );
}
