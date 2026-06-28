import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Application,
  ApplicationStatus,
  STATUS_LABEL,
  STATUS_ORDER,
  applicationDownloadUrl,
  listApplications,
  updateApplication,
} from "./api/applications";

export function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listApplications()
      .then(setApps)
      .finally(() => setLoading(false));
  }, []);

  async function move(app: Application, status: ApplicationStatus) {
    const updated = await updateApplication(app.id, { status });
    setApps((prev) => prev.map((a) => (a.id === app.id ? updated : a)));
  }

  if (loading) return <div className="p-gutter text-on-surface-variant">Loading…</div>;

  return (
    <div className="p-gutter flex flex-col gap-stack-lg">
      <header>
        <h1 className="text-headline-lg font-headline-lg text-on-surface">Applications</h1>
        <p className="text-body-md text-on-surface-variant">
          Every job you've applied to, by stage.
        </p>
      </header>

      {apps.length === 0 ? (
        <div className="border border-outline-variant rounded-xl p-gutter text-on-surface-variant">
          No tracked applications yet. Generate a package and click "I Applied".
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-stack-md">
          {STATUS_ORDER.map((status) => {
            const column = apps.filter((a) => a.status === status);
            return (
              <section key={status} className="flex flex-col gap-stack-sm">
                <h2 className="text-label-md font-medium text-on-surface-variant flex items-center justify-between">
                  <span>{STATUS_LABEL[status]}</span>
                  <span className="text-on-surface-variant/60">{column.length}</span>
                </h2>
                <div className="flex flex-col gap-stack-sm">
                  {column.map((app) => (
                    <article
                      key={app.id}
                      className="bg-surface-container-lowest border border-outline-variant rounded-lg p-stack-md flex flex-col gap-stack-xs"
                    >
                      <div className="text-body-md font-medium text-on-surface">{app.job_title}</div>
                      {app.company && (
                        <div className="text-body-sm text-on-surface-variant">{app.company}</div>
                      )}
                      {app.url && (
                        <a
                          href={app.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-body-sm text-primary hover:underline truncate"
                        >
                          Job posting ↗
                        </a>
                      )}
                      {app.notes && (
                        <p className="text-body-sm text-on-surface-variant line-clamp-3">{app.notes}</p>
                      )}
                      {app.slug && (
                        <div className="flex flex-wrap items-center gap-stack-sm pt-stack-xs">
                          <Link
                            to={`/packages/${encodeURIComponent(app.slug)}`}
                            className="text-label-md text-primary hover:underline"
                          >
                            View package
                          </Link>
                          {app.cv_markdown && (
                            <a
                              href={applicationDownloadUrl(app.id, "cv")}
                              className="text-label-md text-primary hover:underline"
                            >
                              Download CV
                            </a>
                          )}
                          {app.cover_letter_markdown && (
                            <a
                              href={applicationDownloadUrl(app.id, "cover")}
                              className="text-label-md text-primary hover:underline"
                            >
                              Download Cover
                            </a>
                          )}
                        </div>
                      )}
                      <div className="flex items-center justify-end pt-stack-xs">
                        <select
                          value={app.status}
                          onChange={(e) => move(app, e.target.value as ApplicationStatus)}
                          className="bg-surface border border-outline-variant rounded px-stack-xs py-[2px] text-label-md text-on-surface"
                        >
                          {STATUS_ORDER.map((s) => (
                            <option key={s} value={s}>
                              {STATUS_LABEL[s]}
                            </option>
                          ))}
                        </select>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
