import { useEffect, useState } from "react";

type StatsResponse = {
  applications_total: number;
  cost_per_app_avg_usd: string;
  cost_per_app_p95_usd: string;
  monthly_spend_usd: string;
  drift_catch_rate: string;
  override_rate: string;
  interview_conversion_rate_30app: string;
  cost_regression_window: boolean;
  n?: number;
};

type State =
  | { kind: "loading" }
  | { kind: "ready"; stats: StatsResponse }
  | { kind: "error"; message: string };

const INSUFFICIENT = "insufficient_data";

function formatUsd(value: string): string {
  // Sidecar Decimal strings keep six trailing zeros; trim to two for display.
  const num = Number.parseFloat(value);
  if (Number.isNaN(num)) return `$${value}`;
  return `$${num.toFixed(2)}`;
}

function formatRate(value: string): string {
  if (value === INSUFFICIENT) return INSUFFICIENT;
  const num = Number.parseFloat(value);
  if (Number.isNaN(num)) return value;
  return `${(num * 100).toFixed(1)}%`;
}

function Metric({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: "regression" | null;
}) {
  const valueClass =
    emphasis === "regression"
      ? "text-headline-md font-headline-md text-error"
      : "text-headline-md font-headline-md text-on-surface";
  return (
    <div className="flex flex-col gap-stack-xs">
      <span className="text-label-md font-label-md uppercase text-on-surface-variant tracking-wider">
        {label}
      </span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}

export function StatsCard() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/stats");
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
        setState({ kind: "ready", stats: body as StatsResponse });
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

  if (state.kind === "loading") {
    return (
      <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter">
        <div className="text-body-md font-body-md text-on-surface-variant">
          Loading stats...
        </div>
      </section>
    );
  }

  if (state.kind === "error") {
    return (
      <section className="bg-surface-container-lowest border border-error rounded-xl p-gutter">
        <div className="text-body-md font-body-md text-error">
          Stats unavailable: {state.message}
        </div>
      </section>
    );
  }

  const { stats } = state;

  const avgCost = formatUsd(stats.cost_per_app_avg_usd);
  const monthlySpend = formatUsd(stats.monthly_spend_usd);
  const driftCatch = formatRate(stats.drift_catch_rate);

  let interviewLabel: string;
  if (stats.interview_conversion_rate_30app === INSUFFICIENT) {
    interviewLabel = `Insufficient data (${stats.n ?? 0}/30)`;
  } else {
    interviewLabel = formatRate(stats.interview_conversion_rate_30app);
  }

  const regression = stats.cost_regression_window ? "regression" : null;

  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter flex flex-col gap-stack-md">
      <div className="flex items-baseline justify-between">
        <h4 className="text-headline-md font-headline-md text-on-surface">
          Pipeline stats
        </h4>
        <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
          {stats.applications_total} application
          {stats.applications_total === 1 ? "" : "s"}
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-stack-md">
        <Metric label="Avg cost / app" value={avgCost} emphasis={regression} />
        <Metric label="Monthly spend" value={monthlySpend} />
        <Metric label="Drift-catch rate" value={driftCatch} />
        <Metric label="Interview rate (30)" value={interviewLabel} />
      </div>
      {stats.cost_regression_window && (
        <div className="border border-error rounded-lg p-stack-md text-error text-body-md font-body-md">
          Cost regression: average cost-per-application exceeds the $0.25 NFR4
          target.
        </div>
      )}
    </section>
  );
}
