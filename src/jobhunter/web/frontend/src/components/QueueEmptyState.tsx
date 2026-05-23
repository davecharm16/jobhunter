export function QueueEmptyState() {
  return (
    <div className="flex flex-col items-center gap-stack-sm px-gutter py-stack-lg text-center">
      <span className="text-headline-md font-headline-md text-on-surface">
        No applications yet
      </span>
      <p className="text-body-md font-body-md text-on-surface-variant max-w-md">
        Paste a JD on the home surface to start. Tailored packages and their
        drift verdicts will land here as soon as the pipeline finishes.
      </p>
      <a
        href="#paste-panel"
        className="text-primary text-body-md font-body-md font-medium hover:underline"
      >
        Jump to the paste panel below
      </a>
    </div>
  );
}
