type Props = {
  heldCount: number;
};

export function HeldCountCard({ heldCount }: Props) {
  const isEmpty = heldCount === 0;
  const valueClass = isEmpty
    ? "text-display font-display text-on-surface-variant"
    : "text-display font-display text-on-surface";
  const subtitle = isEmpty
    ? "Queue is clear"
    : heldCount === 1
      ? "Application waiting for your review"
      : "Applications waiting for your review";

  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter shadow-sm flex flex-col gap-stack-sm">
      <div className="flex items-baseline justify-between">
        <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
          Held packages
        </span>
      </div>
      <span className={valueClass}>{heldCount}</span>
      <span className="text-body-md font-body-md text-on-surface-variant">
        {subtitle}
      </span>
    </section>
  );
}
