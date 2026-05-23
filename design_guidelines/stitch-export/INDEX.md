# Stitch Export — Drift-Checked Job Hunter

**Source:** Stitch project `14722049854544467629`
**Exported:** 2026-05-23
**Design system:** Inter typography, deep navy + vibrant blue palette, fixed 260px sidebar + fluid content, 8px base grid, soft 0.25rem corners. Full tokens + component guidance in `design.md`.

## Screens

Each screen has a rendered HTML mockup in `html/` and a PNG screenshot in `screenshots/`. The HTML is the source of truth for layout, component composition, and exact Tailwind classes.

| # | Screen | Stitch screen ID | HTML | Screenshot | Maps to |
|---|--------|------------------|------|------------|---------|
| 1 | Job Hunter Dashboard | `c0f54188212a4e199fc51377f3e8c6ed` | [html/01-dashboard.html](html/01-dashboard.html) | [screenshots/01-dashboard.png](screenshots/01-dashboard.png) | Epic 6 (held-package queue + status) |
| 2 | Settings & Canonical CV | `9aaf03454bf24f28932a74162e7baa47` | [html/02-settings-canonical-cv.html](html/02-settings-canonical-cv.html) | [screenshots/02-settings-canonical-cv.png](screenshots/02-settings-canonical-cv.png) | Epic 1.1 / 2.1 (CV editor with tags + high-impact flag) |
| 3 | Job Alerts & Automated Scans | `89f441f5b4b7453b80a877c8fdf9e7ac` | [html/03-job-alerts-automated-scans.html](html/03-job-alerts-automated-scans.html) | [screenshots/03-job-alerts-automated-scans.png](screenshots/03-job-alerts-automated-scans.png) | Epic 7 (n8n scheduled flows) |
| 4 | JD Pipeline & Tailoring | `f36627538803464e9052bf289d0d6853` | [html/04-jd-pipeline-tailoring.html](html/04-jd-pipeline-tailoring.html) | [screenshots/04-jd-pipeline-tailoring.png](screenshots/04-jd-pipeline-tailoring.png) | Epic 2 (paste pipeline + artifact viewer) |
| 5 | Drift Check Diagnostics | `cf5b36f115ef4f51b278595460058587` | [html/05-drift-check-diagnostics.html](html/05-drift-check-diagnostics.html) | [screenshots/05-drift-check-diagnostics.png](screenshots/05-drift-check-diagnostics.png) | Epics 3 + 4 + 5 (drift checks) |
| – | image.png (reference image, no HTML) | `10709945769664221223` | — | [screenshots/06-image-extra.png](screenshots/06-image-extra.png) | reference only |

## How dev-story sessions should use this

When implementing an Epic 8 story (per `_bmad-output/planning-artifacts/epics.md`):
1. Open the screen's HTML file — it has the exact DOM structure + Tailwind classes Stitch generated.
2. Cross-reference the screenshot for visual intent.
3. Pull design tokens from `design.md` (colors, typography, spacing) and wire them into the Tailwind config.
4. Do **not** copy the HTML verbatim — Stitch output is single-file with inlined assets. Decompose into React components that match the existing project's `src/jobhunter/` module conventions.

## Constraints carried from PRD (do not violate)

- Web UI binds to `127.0.0.1` only. Never `0.0.0.0`.
- No auth in v1 (single-user, localhost).
- No outbound submission to job boards — "Approve" actions only call the override CLI.
- Backend wraps existing CLI logic via FastAPI; no new persistence layer (read sprint-status.yaml + sidecar JSON files directly).
- Design tokens **must** come from `design.md` — no ad-hoc color/spacing values in component code.
