import { NavLink } from "react-router-dom";

const NAV_ITEMS: Array<{ label: string; to: string }> = [
  { label: "Dashboard", to: "/" },
  { label: "JD Pipeline", to: "/jd-pipeline" },
  { label: "CV Tailoring", to: "/cv-tailoring" },
  { label: "Drift Checks", to: "/drift-checks" },
  { label: "Job Alerts", to: "/job-alerts" },
  { label: "Settings", to: "/settings" },
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
          <NavLink
            key={item.label}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              isActive
                ? "flex items-center gap-stack-sm px-stack-md py-stack-sm text-primary font-bold border-l-[3px] border-primary bg-secondary-container rounded-r-lg"
                : "flex items-center gap-stack-sm px-stack-md py-stack-sm text-on-surface-variant hover:bg-surface-container-high border-l-[3px] border-transparent rounded-r-lg"
            }
          >
            <span className="text-body-md font-body-md">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
