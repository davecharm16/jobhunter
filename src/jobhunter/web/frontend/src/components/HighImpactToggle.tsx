type Props = {
  value: boolean | undefined;
  onChange: (next: boolean) => void;
  label?: string;
};

export function HighImpactToggle({ value, onChange, label = "High impact" }: Props) {
  const active = value === true;
  return (
    <label className="inline-flex items-center gap-stack-sm cursor-pointer select-none">
      <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
        {label}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={active}
        onClick={() => onChange(!active)}
        className={
          active
            ? "relative inline-flex items-center w-10 h-5 rounded-full bg-primary border border-primary transition-colors"
            : "relative inline-flex items-center w-10 h-5 rounded-full bg-surface-container-high border border-outline-variant transition-colors"
        }
      >
        <span
          className={
            active
              ? "absolute right-1 top-0.5 w-4 h-4 rounded-full bg-on-primary shadow-sm transition-transform"
              : "absolute left-1 top-0.5 w-4 h-4 rounded-full bg-surface-container-lowest shadow-sm transition-transform"
          }
        />
      </button>
    </label>
  );
}
