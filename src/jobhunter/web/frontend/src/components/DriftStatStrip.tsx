/**
 * DriftStatStrip — Story gap 05-10
 *
 * Three compact stats derived from the drift report displayed near the top
 * of the drift detail view:
 *   - Fabrication Score  (unsourced / total claims + verdict)
 *   - Content Loss       (dropped entries count + verdict)
 *   - Keyword Density    (density violations count + channel)
 *
 * Follows the Stitch design: horizontal pill row with a divider between each
 * stat. Uses design tokens via Tailwind — no ad-hoc hex.
 */

import type { ContentLossBlock } from "./ContentLossSection";
import type { KeywordStuffingBlock } from "./KeywordStuffingSection";

type FabricationCheck = {
  verdict: "pass" | "fail";
  claims_total: number;
  claims_sourced: number;
  claims_unsourced: number;
};

type Props = {
  fabrication?: FabricationCheck | null;
  contentLoss?: ContentLossBlock | null;
  keywordStuffing?: KeywordStuffingBlock | null;
};

export function DriftStatStrip({ fabrication, contentLoss, keywordStuffing }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-stack-md rounded-xl border border-outline-variant bg-surface-container-lowest px-stack-md py-stack-sm shadow-sm">
      <StatItem
        label="Fabrication Score"
        value={fabricationValue(fabrication)}
        tone={fabrication?.verdict === "pass" ? "good" : fabrication?.verdict === "fail" ? "bad" : "neutral"}
      />
      <Divider />
      <StatItem
        label="Content Loss"
        value={contentLossValue(contentLoss)}
        tone={contentLoss?.verdict === "pass" ? "good" : contentLoss?.verdict === "fail" ? "bad" : "neutral"}
      />
      <Divider />
      <StatItem
        label="Keyword Density"
        value={keywordDensityValue(keywordStuffing)}
        tone={keywordStuffing?.verdict === "pass" ? "good" : keywordStuffing?.verdict === "fail" ? "bad" : "neutral"}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fabricationValue(fab?: FabricationCheck | null): string {
  if (!fab) return "Pending";
  if (fab.claims_total === 0) return "No claims";
  const pct = Math.round((fab.claims_sourced / fab.claims_total) * 100);
  if (fab.verdict === "pass") return `${pct}% sourced`;
  return `${fab.claims_unsourced} unsourced / ${fab.claims_total}`;
}

function contentLossValue(cl?: ContentLossBlock | null): string {
  if (!cl) return "Pending";
  if (cl.verdict === "pass") return "0% lost";
  const dropped = cl.dropped_entries.length;
  const total = cl.preserved_entries.length + dropped;
  if (total === 0) return "No entries";
  const pct = Math.round((dropped / total) * 100);
  return `${pct}% lost (${dropped} dropped)`;
}

function keywordDensityValue(ks?: KeywordStuffingBlock | null): string {
  if (!ks) return "Pending";
  if (ks.verdict === "pass") return "Clean";
  const violations = ks.density_violations.length;
  const dumps = ks.dump_paragraph_locations.length;
  const parts: string[] = [];
  if (violations > 0) parts.push(`${violations} density`);
  if (dumps > 0) parts.push(`${dumps} dump${dumps === 1 ? "" : "s"}`);
  return parts.length > 0 ? parts.join(" · ") : "Fail";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type Tone = "good" | "bad" | "neutral";

const VALUE_CLASS: Record<Tone, string> = {
  good: "text-body-lg font-body-lg font-semibold text-[#15803d]",
  bad: "text-body-lg font-body-lg font-semibold text-error",
  neutral: "text-body-lg font-body-lg font-semibold text-on-surface-variant",
};

function StatItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: Tone;
}) {
  return (
    <div className="flex flex-col gap-[2px]">
      <span className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
        {label}
      </span>
      <span className={VALUE_CLASS[tone]}>{value}</span>
    </div>
  );
}

function Divider() {
  return (
    <div className="hidden sm:block w-px h-8 bg-outline-variant self-center" aria-hidden="true" />
  );
}
