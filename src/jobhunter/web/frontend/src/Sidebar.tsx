import { NavLink } from "react-router-dom";

// Inline SVG icons — kept minimal; no external icon dependency needed.
const IconDashboard = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor" opacity="0.9" />
    <rect x="13" y="3" width="8" height="8" rx="1.5" fill="currentColor" opacity="0.6" />
    <rect x="3" y="13" width="8" height="8" rx="1.5" fill="currentColor" opacity="0.6" />
    <rect x="13" y="13" width="8" height="8" rx="1.5" fill="currentColor" opacity="0.9" />
  </svg>
);

const IconScans = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
    <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const IconSettings = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
    <path
      d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>
);

const IconDrift = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconApplications = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="2" />
    <line x1="8" y1="10" x2="16" y2="10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <line x1="8" y1="14" x2="16" y2="14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <line x1="8" y1="18" x2="12" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const NAV_ITEMS: Array<{ label: string; to: string; Icon: () => JSX.Element }> = [
  { label: "Dashboard", to: "/", Icon: IconDashboard },
  { label: "Scans", to: "/scans", Icon: IconScans },
  { label: "Drift Checks", to: "/drift", Icon: IconDrift },
  { label: "Applications", to: "/applications", Icon: IconApplications },
  { label: "Settings", to: "/settings", Icon: IconSettings },
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
        {NAV_ITEMS.map(({ label, to, Icon }) => (
          <NavLink
            key={label}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              isActive
                ? "flex items-center gap-stack-sm px-stack-md py-stack-sm text-primary font-bold border-l-[3px] border-primary bg-secondary-container rounded-r-lg"
                : "flex items-center gap-stack-sm px-stack-md py-stack-sm text-on-surface-variant hover:bg-surface-container-high border-l-[3px] border-transparent rounded-r-lg"
            }
          >
            <Icon />
            <span className="text-body-md font-body-md">{label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
