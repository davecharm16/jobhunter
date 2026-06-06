import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="p-gutter max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      <div>
        <h3 className="text-display font-display text-on-surface mb-stack-sm">
          404 — Page not found
        </h3>
        <p className="text-body-lg font-body-lg text-on-surface-variant mb-stack-md">
          This path doesn't match any page in Job Hunter.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-stack-sm px-stack-md py-stack-sm text-primary font-bold border border-primary rounded-lg hover:bg-secondary-container"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  );
}
