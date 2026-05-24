/**
 * ScansPage — Story 7.5
 *
 * Browser view of the n8n ingest flows' status (Upwork, OnlineJobs.ph,
 * LinkedIn email). Reads GET /api/scans and renders one FlowCard per flow
 * matching Stitch screen 03's layout. The backend never exposes inbox
 * credentials, n8n auth tokens, IMAP passwords, or any .env value — this
 * page consumes only the operational telemetry derived from per-application
 * metadata sidecars on disk.
 */

import { useEffect, useState } from "react";
import { FlowCard, type FlowTelemetry } from "./components/FlowCard";

type ScansResponse = {
  flows: FlowTelemetry[];
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; payload: ScansResponse }
  | { kind: "error"; message: string };

export function ScansPage() {
  const [state, setState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/scans");
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          setState({
            kind: "error",
            message:
              typeof body.detail === "string"
                ? body.detail
                : JSON.stringify(body.detail),
          });
          return;
        }
        setState({ kind: "ready", payload: body as ScansResponse });
      } catch (exc) {
        if (!cancelled) {
          setState({ kind: "error", message: String(exc) });
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="p-gutter max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      <header>
        <h3 className="text-display font-display text-on-surface mb-stack-sm">
          Job Alerts &amp; Automated Scans
        </h3>
        <p className="text-body-lg font-body-lg text-on-surface-variant">
          Health of the three n8n ingest flows. Operational telemetry only —
          no inbox credentials, n8n tokens, or .env values surface here.
        </p>
      </header>

      {state.kind === "loading" && (
        <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter shadow-sm">
          <p className="text-body-md font-body-md text-on-surface-variant">
            Loading scan telemetry...
          </p>
        </section>
      )}

      {state.kind === "error" && (
        <section className="bg-surface-container-lowest border border-error rounded-xl p-gutter shadow-sm">
          <p className="text-body-md font-body-md text-error">
            Scan telemetry unavailable: {state.message}
          </p>
        </section>
      )}

      {state.kind === "ready" && (
        <section className="grid grid-cols-1 md:grid-cols-3 gap-stack-md">
          {state.payload.flows.map((flow) => (
            <FlowCard key={flow.flow_name} flow={flow} />
          ))}
        </section>
      )}
    </div>
  );
}
