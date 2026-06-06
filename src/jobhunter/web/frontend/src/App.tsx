import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { PastePanel } from "./PastePanel";
import { SettingsPage } from "./SettingsPage";
import { StatsCard } from "./StatsCard";
import { PackagePage } from "./PackagePage";
import { DriftPage } from "./DriftPage";
import { DriftHistoryPage } from "./DriftHistoryPage";
import { ScansPage } from "./ScansPage";
import { NotFound } from "./NotFound";
import { HeldCountCard } from "./components/HeldCountCard";
import { type QueueEntry } from "./components/RecentPackagesTable";
import { PipelineCard } from "./components/PipelineCard";
import { QueueEmptyState } from "./components/QueueEmptyState";

type QueueResponse = {
  held_count: number;
  recent: QueueEntry[];
};

type QueueState =
  | { kind: "loading" }
  | { kind: "ready"; queue: QueueResponse }
  | { kind: "error"; message: string };

type GreetingState =
  | { kind: "loading" }
  | { kind: "ready"; firstName: string }
  | { kind: "error" };

function useGreeting(): GreetingState {
  const [state, setState] = useState<GreetingState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/canonical-cv");
        if (!response.ok) {
          if (!cancelled) setState({ kind: "error" });
          return;
        }
        const body = await response.json();
        if (cancelled) return;
        const fullName: string =
          typeof body?.basics?.name === "string" ? body.basics.name : "";
        const firstName = fullName.trim().split(/\s+/)[0] || "";
        setState(
          firstName ? { kind: "ready", firstName } : { kind: "error" },
        );
      } catch {
        if (!cancelled) setState({ kind: "error" });
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

function DashboardPage() {
  const [jdText, setJdText] = useState("");
  const [queueState, setQueueState] = useState<QueueState>({ kind: "loading" });
  const greetingState = useGreeting();

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

  const greetingName =
    greetingState.kind === "ready" ? greetingState.firstName : null;

  return (
    <div className="p-gutter max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      {/* 01-20: Personalized greeting */}
      <div>
        <h3 className="text-display font-display text-on-surface mb-stack-sm">
          {greetingName ? `Hello, ${greetingName}!` : "Hello!"}
        </h3>
        <p className="text-body-lg font-body-lg text-on-surface-variant">
          Ready to land your next role? Let&apos;s start tailoring.
        </p>
      </div>

      {/* 01-10: Prominent "Start New Application" card at the top */}
      <PastePanel jdText={jdText} setJdText={setJdText} />

      {/* 01-22 + 01-11 + 01-13: Three discrete metric cards with icons */}
      <StatsCard />

      {/* Pipeline section */}
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
            <section className="bg-surface-container-lowest border border-outline-variant rounded-xl shadow-sm overflow-hidden">
              <header className="flex items-center justify-between px-gutter py-stack-md border-b border-outline-variant bg-surface-container-low">
                <h3 className="text-headline-md font-headline-md text-on-surface">
                  Application Pipeline
                </h3>
                <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
                  {recent.length} shown
                </span>
              </header>
              {recent.length === 0 ? (
                <QueueEmptyState />
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-stack-md p-gutter">
                  {recent.map((entry) => (
                    <PipelineCard key={entry.slug} entry={entry} />
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </section>
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
            <Route path="/drift" element={<DriftHistoryPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
