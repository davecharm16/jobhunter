const NAV_ITEMS = [
  { label: "Dashboard", active: true },
  { label: "JD Pipeline", active: false },
  { label: "CV Tailoring", active: false },
  { label: "Drift Checks", active: false },
  { label: "Job Alerts", active: false },
];

export function Sidebar() {
  return (
    <aside className="hidden md:flex flex-col w-sidebar-width h-screen sticky left-0 top-0 py-stack-lg border-r border-outline-variant bg-surface-container-low">
      <div className="px-gutter mb-stack-lg">
        <h1 className="text-headline-lg font-headline-lg font-bold text-on-surface">
          Job Hunter
        </h1>
      </div>
      <div className="px-gutter mb-stack-md">
        <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
          Menu
        </span>
      </div>
      <nav className="flex-1 flex flex-col gap-stack-xs px-stack-md">
        {NAV_ITEMS.map((item) => (
          <a
            key={item.label}
            href="#"
            className={
              item.active
                ? "flex items-center gap-stack-sm px-stack-md py-stack-sm text-primary font-bold border-l-4 border-primary bg-secondary-container rounded-r-lg"
                : "flex items-center gap-stack-sm px-stack-md py-stack-sm text-on-surface-variant hover:bg-surface-container-high border-l-4 border-transparent rounded-r-lg"
            }
          >
            <span className="text-body-md font-body-md">{item.label}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}
