import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { PastePanel } from "./PastePanel";
import { SettingsPage } from "./SettingsPage";
import { StatsCard } from "./StatsCard";
import { PackagePage } from "./PackagePage";
import { DriftPage } from "./DriftPage";
import { ScansPage } from "./ScansPage";
import { HeldCountCard } from "./components/HeldCountCard";
import {
  RecentPackagesTable,
  type QueueEntry,
} from "./components/RecentPackagesTable";

type QueueResponse = {
  held_count: number;
  recent: QueueEntry[];
};

type QueueState =
  | { kind: "loading" }
  | { kind: "ready"; queue: QueueResponse }
  | { kind: "error"; message: string };

function DashboardPage() {
  const [jdText, setJdText] = useState("");
  const [queueState, setQueueState] = useState<QueueState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/queue");
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          setQueueState({
            kind: "error",
            message:
              typeof body.detail === "string"
                ? body.detail
                : JSON.stringify(body.detail),
          });
          return;
        }
        setQueueState({ kind: "ready", queue: body as QueueResponse });
      } catch (exc) {
        if (!cancelled) {
          setQueueState({ kind: "error", message: String(exc) });
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const heldCount =
    queueState.kind === "ready" ? queueState.queue.held_count : 0;
  const recent =
    queueState.kind === "ready" ? queueState.queue.recent : [];

  return (
    <div className="p-gutter max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      <div>
        <h3 className="text-display font-display text-on-surface mb-stack-sm">
          Dashboard
        </h3>
        <p className="text-body-lg font-body-lg text-on-surface-variant">
          What does Job Hunter want from you right now? Held packages, recent
          verdicts, and a fast path to tailor the next JD.
        </p>
      </div>
      <StatsCard />
      <section className="grid grid-cols-1 md:grid-cols-3 gap-stack-md">
        <HeldCountCard heldCount={heldCount} />
        <div className="md:col-span-2 flex flex-col">
          {queueState.kind === "loading" && (
            <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter shadow-sm">
              <p className="text-body-md font-body-md text-on-surface-variant">
                Loading queue...
              </p>
            </section>
          )}
          {queueState.kind === "error" && (
            <section className="bg-surface-container-lowest border border-error rounded-xl p-gutter shadow-sm">
              <p className="text-body-md font-body-md text-error">
                Queue unavailable: {queueState.message}
              </p>
            </section>
          )}
          {queueState.kind === "ready" && (
            <RecentPackagesTable entries={recent} />
          )}
        </div>
      </section>
      <div id="paste-panel">
        <PastePanel jdText={jdText} setJdText={setJdText} />
      </div>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-full flex bg-surface text-on-surface">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0">
          <header className="h-16 px-gutter flex items-center border-b border-outline-variant bg-surface">
            <h2 className="text-headline-lg font-headline-lg text-on-surface">
              Job Hunter
            </h2>
          </header>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/packages/:slug" element={<PackagePage />} />
            <Route path="/packages/:slug/drift" element={<DriftPage />} />
            <Route path="/scans" element={<ScansPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
