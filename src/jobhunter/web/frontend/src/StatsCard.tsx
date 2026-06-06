import { useEffect, useState } from "react";

type StatsResponse = {
  applications_total: number;
  cost_per_app_avg_usd: string;
  cost_per_app_p95_usd: string;
  monthly_spend_usd: string;
  drift_catch_rate: string;
  drift_catches_total?: number;
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
  const num = Number.parseFloat(value);
  if (Number.isNaN(num)) return `$${value}`;
  return `$${num.toFixed(2)}`;
}

function formatRate(value: string): string {
  if (value === INSUFFICIENT) return "—";
  const num = Number.parseFloat(value);
  if (Number.isNaN(num)) return value;
  return `${(num * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Inline SVG icons (monitoring / policy / payments motif from design)
// ---------------------------------------------------------------------------

function IconMonitoring() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 -960 960 960"
      aria-hidden="true"
      className="w-5 h-5 fill-current"
    >
      <path d="M120-200v-80h80v-280q0-83 50-147.5T380-792v-28q0-25 17.5-42.5T440-880h80q25 0 42.5 17.5T580-820v28q80 20 130 84.5T760-560v280h80v80H120Zm360-300Zm0 420q-33 0-56.5-23.5T400-160h160q0 33-23.5 56.5T480-80ZM280-280h400v-280q0-83-58.5-141.5T480-760q-83 0-141.5 58.5T280-560v280Z" />
    </svg>
  );
}

function IconPolicy() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 -960 960 960"
      aria-hidden="true"
      className="w-5 h-5 fill-current"
    >
      <path d="M480-80q-139-35-229.5-159.5T160-516v-244l320-120 320 120v244q0 152-90.5 276.5T480-80Zm0-84q97-30 162-118.5T718-480H480v-315l-240 90v207q0 7 .5 13.5T242-480h238v316Z" />
    </svg>
  );
}

function IconPayments() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 -960 960 960"
      aria-hidden="true"
      className="w-5 h-5 fill-current"
    >
      <path d="M560-440q-50 0-85-35t-35-85q0-50 35-85t85-35q50 0 85 35t35 85q0 50-35 85t-85 35ZM280-320q-33 0-56.5-23.5T200-400v-320q0-33 23.5-56.5T280-800h560q33 0 56.5 23.5T920-720v320q0 33-23.5 56.5T840-320H280Zm80-80h400q0-33 23.5-56.5T840-480v-160q-33 0-56.5-23.5T760-720H360q0 33-23.5 56.5T280-640v160q33 0 56.5 23.5T360-400Zm440 240H120q-33 0-56.5-23.5T40-240v-440h80v440h680v80ZM280-400v-320 320Z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Individual metric card
// ---------------------------------------------------------------------------

type MetricCardProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  caption: string;
  emphasis?: "regression" | null;
};

function MetricCard({ icon, label, value, caption, emphasis }: MetricCardProps) {
  const valueClass =
    emphasis === "regression"
      ? "text-headline-lg font-headline-lg text-error font-bold"
      : "text-headline-lg font-headline-lg text-on-surface font-bold";

  return (
    <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-md shadow-sm flex flex-col gap-stack-xs">
      <div className="flex justify-between items-center text-on-surface-variant">
        <span className="text-body-md font-body-md font-medium">{label}</span>
        <span className="text-on-surface-variant">{icon}</span>
      </div>
      <div className={valueClass}>{value}</div>
      <div className="text-label-md font-label-md text-on-surface-variant flex items-center gap-stack-xs">
        {caption}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatsCard — three discrete metric cards
// ---------------------------------------------------------------------------

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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-stack-md">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-md shadow-sm"
          >
            <div className="text-body-md font-body-md text-on-surface-variant animate-pulse">
              Loading...
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-stack-md">
        <div className="md:col-span-3 bg-surface-container-lowest border border-error rounded-xl p-stack-md">
          <div className="text-body-md font-body-md text-error">
            Stats unavailable: {state.message}
          </div>
        </div>
      </div>
    );
  }

  const { stats } = state;

  // --- Interview rate card ---
  let interviewValue: string;
  let interviewCaption: string;
  if (stats.interview_conversion_rate_30app === INSUFFICIENT) {
    interviewValue = "—";
    interviewCaption = `Insufficient data (${stats.n ?? 0}/30 apps)`;
  } else {
    interviewValue = formatRate(stats.interview_conversion_rate_30app);
    interviewCaption = `${stats.applications_total} application${stats.applications_total === 1 ? "" : "s"} tracked`;
  }

  // --- Drift catches card ---
  // Prefer explicit total count; fall back to deriving from rate × total
  const driftCatchesTotal =
    typeof stats.drift_catches_total === "number"
      ? stats.drift_catches_total
      : (() => {
          const rate = Number.parseFloat(stats.drift_catch_rate);
          if (Number.isNaN(rate)) return null;
          return Math.round(rate * stats.applications_total);
        })();

  const driftValue =
    driftCatchesTotal !== null ? String(driftCatchesTotal) : "—";

  // --- Spend card ---
  const monthlySpend = formatUsd(stats.monthly_spend_usd);
  const regression = stats.cost_regression_window ? "regression" : null;

  return (
    <div className="flex flex-col gap-stack-md">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-stack-md">
        <MetricCard
          icon={<IconMonitoring />}
          label="Interview Rate"
          value={interviewValue}
          caption={interviewCaption}
        />
        <MetricCard
          icon={<IconPolicy />}
          label="Drift Catches"
          value={driftValue}
          caption="Fabrications prevented"
        />
        <MetricCard
          icon={<IconPayments />}
          label="Total Spend"
          value={monthlySpend}
          caption="API usage cost"
          emphasis={regression}
        />
      </div>
      {stats.cost_regression_window && (
        <div className="border border-error rounded-lg p-stack-md text-error text-body-md font-body-md">
          Cost regression: average cost-per-application exceeds the $0.25 NFR4
          target.
        </div>
      )}
    </div>
  );
}
