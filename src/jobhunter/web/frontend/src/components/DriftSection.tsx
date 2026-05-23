import type { ReactNode } from "react";

type DriftVerdict = "pass" | "fail" | "pending" | "unknown";

type Props = {
  title: string;
  verdict: DriftVerdict;
  subtitle?: string;
  children?: ReactNode;
};

const VERDICT_BADGE: Record<DriftVerdict, string> = {
  pass: "bg-secondary-container text-primary border-primary/20",
  fail: "bg-error-container text-on-error-container border-error/40",
  pending:
    "bg-surface-container text-on-surface-variant border-outline-variant",
  unknown:
    "bg-surface-container text-on-surface-variant border-outline-variant",
};

const VERDICT_LABEL: Record<DriftVerdict, string> = {
  pass: "Pass",
  fail: "Fail",
  pending: "Pending",
  unknown: "Unknown",
};

export function DriftSection({ title, verdict, subtitle, children }: Props) {
  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden shadow-sm">
      <header className="flex items-center justify-between gap-stack-md px-stack-md py-stack-sm border-b border-outline-variant bg-surface-container-low">
        <div className="flex flex-col">
          <h2 className="text-headline-md font-headline-md text-on-surface">
            {title}
          </h2>
          {subtitle && (
            <p className="text-label-md font-label-md text-on-surface-variant mt-stack-xs">
              {subtitle}
            </p>
          )}
        </div>
        <span
          className={`shrink-0 px-stack-sm py-stack-xs rounded-full border text-label-md font-label-md uppercase tracking-wider ${VERDICT_BADGE[verdict]}`}
        >
          {VERDICT_LABEL[verdict]}
        </span>
      </header>
      <div className="p-stack-md flex flex-col gap-stack-md">{children}</div>
    </section>
  );
}

export type { DriftVerdict };
