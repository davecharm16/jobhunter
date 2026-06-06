# Design Gap Checklist

> Generated from a fan-out audit of `design_guidelines/` vs the implemented app.
> **80 gaps total, 20 high-severity.** Each is a feature the design specifies but the app is missing (`missing`) or only partially does (`partial`).

## Overall

Across all five pages the implementation wires up core data and primary flows but consistently omits the persistent app shell (top app bar with search / Create New CV / notifications / avatar, and the sidebar Profile Completion widget) and downgrades rich, designed compositions into plain lists/tables/forms. The largest divergences are structural: the dashboard pipeline renders as a bare table instead of stateful status cards; Settings drops the entire raw Markdown/YAML editor plus API Configuration and Notifications panels in favor of a JSON-Resume form; Job Alerts ships read-only telemetry and omits ~two-thirds of the configurable page (Search Criteria, scanner controls, Integration Status); the JD Pipeline lacks inline JD-tailoring and drift highlights with tooltips; and Drift Checks is a single-package view rather than the designed master/detail history dashboard with a side-by-side semantic diff. 80 distinct gaps total, 20 high severity.

## 01-dashboard

_Core data wiring (held count, stats, recent packages, paste panel) is implemented, but the top app bar, sidebar profile widget, metric iconography/trends, and the rich Application Pipeline status cards are missing._

| ID | Sev | Status | Cat | Feature | What's needed |
|---|---|---|---|---|---|
| `01-dashboard-1` | H | partial | ui | Application Pipeline rendered as a table instead of status cards | Replace the compact 4-column table (slug / source / verdict / when) with the designed 2-column grid of rich pipeline cards (job title, company/source, status badge, divider, drift-health row, action button, hover shadow). |
| `01-dashboard-2` | H | missing | state | Pipeline workflow stage badge (Review / Drift Check / Drafting) missing | Add per-card workflow-stage chips ('Review', 'Drift Check', 'Drafting') with distinct styling; the implementation only renders a terminal verdict badge (Pass/Held/Overridden) and has no workflow-stage concept. |
| `01-dashboard-3` | H | missing | ui | Per-card Drift Health status row missing | Add the divider-separated footer row showing drift health with icon+label per card: 'Drift Health: Pass' (check_circle, green), 'Fabrication Detected' (warning, red), or 'Tailoring in progress...' (pending). |
| `01-dashboard-4` | H | missing | interaction | Per-card context action buttons (View Docs / Fix Issues / Continue) missing | Add state-specific action buttons: 'View Docs' (passing), 'Fix Issues' (failed), 'Continue' (in-progress). The implementation makes the whole row a single link with no distinct per-state actions. |
| `01-dashboard-5` | M | missing | ui | Top app bar search field missing | Add the full-width search input with search icon and 'Search or type a command' placeholder; the header only shows a static 'Job Hunter' title. |
| `01-dashboard-6` | M | missing | flow | 'Create New CV' primary action in top bar missing | Add the primary blue 'Create New CV' button (add_box icon) as the main top-bar CTA; the header has no action buttons. |
| `01-dashboard-7` | M | missing | ui | Notifications bell + unread indicator missing | Add the notifications bell icon with a red unread-dot badge to the top bar. |
| `01-dashboard-8` | M | missing | ui | Sidebar nav items lack icons | Pair each sidebar nav label with its Material Symbol icon (dashboard, timeline, edit_document, check_circle, notifications); links are currently text-only. |
| `01-dashboard-9` | M | missing | ui | Sidebar Profile Completion widget missing | Add the sidebar-bottom profile widget: avatar, user name, 'X% Complete' label, circular progress ring, helper copy, and 'Complete Now' CTA. |
| `01-dashboard-10` | M | partial | ui | 'Start New Application' quick-action card styling/copy/placement differs | Present the JD paste as a prominent top 'Start New Application' card with post_add icon-circle, descriptive subtext, and a 'Begin Tailoring' + arrow_forward button; the PastePanel sits at the bottom with no icon and different copy. |
| `01-dashboard-11` | M | missing | ui | Metric cards missing per-card icons | Add the corner Material Symbol icons (monitoring, policy, payments) to each metric card; metrics currently render as plain label/value pairs with no icons. |
| `01-dashboard-12` | M | missing | data | Interview Rate trend delta indicator missing | Add the green trending_up delta '+2.1% this month' to the Interview Rate card; no month-over-month trend is shown. |
| `01-dashboard-13` | M | partial | data | Drift surfaced as percentage instead of count + 'Fabrications prevented' caption | Show drift as an absolute count ('4') captioned 'Fabrications prevented' rather than a 'Drift-catch rate' percentage. |
| `01-dashboard-14` | M | missing | interaction | Application Pipeline 'View All' link missing | Add the 'View All' link with arrow_outward icon in the pipeline section header; only a '{n} shown' count is shown. |
| `01-dashboard-15` | M | partial | data | Human-readable job title not shown (slug used instead) | Display the role title (e.g. 'Senior Frontend Developer') as the card heading instead of the raw package slug. |
| `01-dashboard-16` | M | partial | data | Company name + work icon on pipeline rows missing | Show employer/company with board source in parentheses, prefixed by a 'work' icon (e.g. 'TechFlow Inc. (LinkedIn)'); only a source-board chip is shown. |
| `01-dashboard-17` | M | missing | ui | Failed-package red ring emphasis missing | Apply the red focus ring (ring-1 ring-fail-red/20) to fabrication/failed cards to draw attention; rows have no per-failure emphasis. |
| `01-dashboard-18` | M | missing | state | In-progress / 'Drafting' application state not represented | Model an actively-drafting state (Drafting badge, pending icon, 'Tailoring in progress...'); the queue only models terminal verdicts. |
| `01-dashboard-19` | L | missing | ui | Mobile menu toggle / mobile header (brand + avatar) missing | Add the mobile-only hamburger toggle, mobile brand label, and mobile profile avatar; the header is desktop-only. |
| `01-dashboard-20` | L | partial | content | Personalized welcome greeting not implemented | Use a personalized display-size greeting 'Hello, Tom!' with subtitle 'Ready to land your next role? Let's start tailoring.' instead of a generic 'Dashboard' heading. |
| `01-dashboard-21` | L | partial | content | 'Total Spend' caption 'API usage cost' missing | Label the spend card 'Total Spend' with caption 'API usage cost' instead of 'Monthly spend' with no caption. |
| `01-dashboard-22` | L | partial | ui | Metrics shown as one combined card instead of three discrete cards | Render three separate bordered metric cards in a 3-column grid rather than a single 'Pipeline stats' card with a 4-metric inner grid. |

## 02-settings-canonical-cv

_Form-based editing and save work, but the design's raw Markdown/YAML editor with Revisions, the API Configuration panel, and the Notifications panel are entirely absent; the implementation ships a structured JSON-Resume form the mockup never shows._

| ID | Sev | Status | Cat | Feature | What's needed |
|---|---|---|---|---|---|
| `02-settings-canonical-cv-1` | H | missing | ui | Raw Markdown/YAML source editor missing | Provide the dark monospace code editor with line numbers and syntax highlighting for editing the canonical CV as Markdown/YAML directly; the implementation only offers a field-by-field JSON Resume form with no raw source view. |
| `02-settings-canonical-cv-2` | H | missing | ui | API Configuration panel missing entirely | Add the right-column 'API Configuration' section (key icon); not rendered at all. |
| `02-settings-canonical-cv-3` | H | missing | data | OpenAI API Key field + edit control missing | Add the readonly masked password input for 'OpenAI API Key (Generation)' with edit (pencil) button and helper 'Stored securely in environment variables.' |
| `02-settings-canonical-cv-4` | H | missing | ui | Notifications panel missing entirely | Add the right-column 'Notifications' section (forum icon) with a master on/off toggle; no notifications configuration exists. |
| `02-settings-canonical-cv-5` | M | missing | interaction | 'Revisions' history button missing | Add the 'Revisions' button (history icon) in the CV source card header for viewing/restoring prior canonical-CV versions. |
| `02-settings-canonical-cv-6` | M | missing | data | Monthly Spend Cap input missing | Add the 'Monthly Spend Cap (USD)' numeric input with a '$' prefix adornment (value 25.00). |
| `02-settings-canonical-cv-7` | M | missing | data | Current Usage readout + progress bar missing | Add the current monthly spend readout ('Current Usage: $12.40') with a horizontal progress bar filled to ~49.6% of the cap. |
| `02-settings-canonical-cv-8` | M | missing | state | Google Chat Webhook card + Active status badge missing | Add the Google Chat webhook integration card showing the webhook URL and a green 'Active' status pill (check_circle icon). |
| `02-settings-canonical-cv-9` | M | missing | interaction | Alert Triggers checkboxes missing | Add the three alert-trigger checkboxes ('New matching job post found' checked, 'Tailored CV generation complete' checked, 'Weekly summary report' unchecked) under an 'Alert Triggers' label. |
| `02-settings-canonical-cv-10` | L | partial | ui | Save button icon and in-card placement differ | Place the Save action (save icon, secondary-container styling) inside the Canonical CV Source card header; the implementation moves Save to the page header and omits the icon (functionality works). |
| `02-settings-canonical-cv-11` | L | partial | content | Page subtitle copy reduced | Restore the integrations/preferences scope in the subtitle; the implementation rewrites it to tags/high-impact, consistent with the missing panels. |
| `02-settings-canonical-cv-12` | L | missing | ui | Top app bar (search + Create New CV + notifications + avatar) missing | Add the shared top bar with search field, 'Create New CV' button, notifications bell, and user avatar; only the 'Job Hunter' title is shown. |
| `02-settings-canonical-cv-13` | L | missing | ui | Sidebar Profile Completion widget missing | Add the sidebar profile-completion widget (avatar, name, 'X% Complete', helper copy, 'Complete Now' CTA with arrow_outward) pinned to the bottom. |

## 03-job-alerts-automated-scans

_Implementation is a read-only telemetry list of three n8n flow cards; the left Global Search Criteria configuration panel, the scanner on/off controls, and the entire right-column Integration Status card (~two-thirds of the page) are missing._

| ID | Sev | Status | Cat | Feature | What's needed |
|---|---|---|---|---|---|
| `03-job-alerts-automated-scans-1` | H | missing | ui | Global Search Criteria configuration section missing entirely | Add the primary left-column panel that configures target job titles, experience level, budget, keywords and scan frequency; the page renders only read-only flow cards. |
| `03-job-alerts-automated-scans-2` | H | missing | interaction | Target Job Titles chip/tag input missing | Add the multi-tag input where titles appear as removable chips (close 'x') plus an 'Add title...' field. |
| `03-job-alerts-automated-scans-3` | H | missing | interaction | Scan Frequency selector missing | Add the scan-frequency control (schedule icon + 'Scan Frequency:' label + select Every 6 Hours / Daily / Weekly); no scheduling control exists. |
| `03-job-alerts-automated-scans-4` | H | missing | interaction | Per-scanner enable/disable toggle missing | Add the on/off pill toggle to each scanner card; flows are passively reported, not controllable. |
| `03-job-alerts-automated-scans-5` | H | missing | ui | Integration Status card missing entirely | Add the right-column 'Integration Status' card reporting backend integration health and the daily scan total. |
| `03-job-alerts-automated-scans-6` | M | missing | ui | Experience Level dropdown missing | Add the Experience Level <select> (Mid-Level to Senior / Junior to Mid-Level / Senior/Lead). |
| `03-job-alerts-automated-scans-7` | M | missing | ui | Budget / Salary Range dropdown missing | Add the Budget/Salary Range <select> with the salary band options. |
| `03-job-alerts-automated-scans-8` | M | missing | ui | Keywords (Must-have) input missing | Add the free-text Keywords input (prefilled 'React, TypeScript, Next.js, Tailwind'). |
| `03-job-alerts-automated-scans-9` | M | missing | interaction | Apply Criteria button missing | Add the primary 'Apply Criteria' action to persist/apply the configured criteria. |
| `03-job-alerts-automated-scans-10` | M | partial | state | Running status indicator (green dot + 'Running') missing | Show a live running state via an emerald status dot + 'Running' on each scanner card; the implementation shows a Pass/Fail/Never-run drift badge instead. |
| `03-job-alerts-automated-scans-11` | M | missing | interaction | 'Edit Scanner' button missing | Add the full-width 'Edit Scanner' action to each scanner card to reconfigure that scanner. |
| `03-job-alerts-automated-scans-12` | M | missing | data | n8n Workflow status row missing | Add the n8n Workflow integration row (n8n icon tile, 'Processing queues' subtitle, 'Active' badge). |
| `03-job-alerts-automated-scans-13` | M | missing | data | JD Webhook Receiver status row missing | Add the 'JD Webhook Receiver' row (webhook icon, 'Last payload: 5m ago', 'Listening' badge). |
| `03-job-alerts-automated-scans-14` | M | missing | data | 'Scans processed today' total missing | Add the aggregate daily scan count ('Scans processed today: 142'); only per-flow counts are shown. |
| `03-job-alerts-automated-scans-15` | M | missing | interaction | 'Force Sync Now' button missing | Add the 'Force Sync Now' action (refresh icon) to manually trigger a sync. |
| `03-job-alerts-automated-scans-16` | M | missing | ui | Two-column 8/4 layout not implemented | Adopt the 12-column grid (8-col left criteria+scanners, 4-col right integration status); the implementation is a single full-width 3-up card grid. |
| `03-job-alerts-automated-scans-17` | L | missing | interaction | Reset (criteria) link missing | Add the 'Reset' link in the Search Criteria header to clear configured criteria. |
| `03-job-alerts-automated-scans-18` | L | partial | ui | Provider icon/avatar on scanner cards missing | Give each scanner a branded avatar tile (e.g. 'U' Upwork, 'in' LinkedIn); the implementation shows a plain text label and raw flow_name. |
| `03-job-alerts-automated-scans-19` | L | missing | data | Scanner keyword/title summary line missing | Show the configured search terms per scanner ('Keywords: React, Next.js' / 'Titles: Frontend Dev'); only ingest count + drift status are shown. |
| `03-job-alerts-automated-scans-20` | L | missing | ui | Left primary accent bar on scanner cards missing | Add the 1px full-height primary accent bar on the left edge of each scanner card; cards use a plain border. |
| `03-job-alerts-automated-scans-21` | L | partial | content | Header subtitle copy differs from design | Reframe the subtitle as configurable ('Configure automated scans across Upwork, LinkedIn, and OnlineJobs.ph.') rather than read-only telemetry. |

## 04-jd-pipeline-tailoring

_The two-pane JD/artifact layout, tab switching, and download/copy actions are present, but the app shell, the design's JD-signal presentation, and the code-editor artifact view with inline JD-tailoring and drift highlights are missing._

| ID | Sev | Status | Cat | Feature | What's needed |
|---|---|---|---|---|---|
| `04-jd-pipeline-tailoring-1` | H | missing | interaction | Inline JD-tailoring highlights with tooltips missing | Highlight artifact phrases tailored to JD must-haves with a secondary-container background, dashed primary underline, and a 'Tailored to JD Must-Have' hover tooltip; MarkdownRenderer applies no such highlight. |
| `04-jd-pipeline-tailoring-2` | H | partial | interaction | Inline drift/hallucination highlight with original-vs-claimed tooltip missing | Highlight fabricated text inline (error-container background, dashed error underline) with a tooltip comparing original vs claimed; the implementation only draws left-margin ticks (MarginDiffTicks) whose popover shows claim_text + reason with no inline highlight or comparison. |
| `04-jd-pipeline-tailoring-3` | M | missing | ui | Persistent 260px sidebar navigation missing | Add the fixed left SideNavBar (260px) with wordmark and nav items (Dashboard, JD Pipeline active with border-l-4, CV Tailoring, Drift Checks, Job Alerts); the page shows only a content column with a text breadcrumb. |
| `04-jd-pipeline-tailoring-4` | M | missing | ui | Top app bar (search, Create New CV, notifications, avatar) missing | Add the sticky TopAppBar with search input, 'Create New CV' button, notifications bell, and avatar. |
| `04-jd-pipeline-tailoring-5` | M | partial | content | JD header shows slug instead of job title + company/location | Head the JD-signals pane with the parsed job title (headline-md) and a company-bullet-location line with a business icon (e.g. 'Senior Frontend Engineer' / 'TechCorp Inc. • Remote'); the implementation shows the raw slug and a 'Source board' line. |
| `04-jd-pipeline-tailoring-6` | M | partial | ui | Red Flags not shown as a prominent left-pane card with icons/reasons | Render Red Flags as a dedicated left-pane card (error styling, warning header icon, per-item close icon, parenthetical risk reason); the implementation lists them plainly inside the right-hand MetadataSidebar. |
| `04-jd-pipeline-tailoring-7` | M | partial | data | Budget Range and Expected Tone stat cards missing in JD pane | Surface 'BUDGET RANGE' and 'EXPECTED TONE' as side-by-side JD-signal stat cards for all boards; the implementation only shows them inside an Upwork-only 'Upwork signals' card. |
| `04-jd-pipeline-tailoring-8` | M | partial | ui | Code-editor artifact view with line numbers and syntax highlighting missing | Display the artifact as a monospace line-numbered editor (gutter 1-15) with markdown syntax highlighting; the implementation renders fully formatted markdown with no gutter or raw-source presentation. |
| `04-jd-pipeline-tailoring-9` | L | missing | ui | Profile Completion widget missing | Add the sidebar Profile Completion widget (avatar, name, '62% Complete', 'Complete Now' button). |
| `04-jd-pipeline-tailoring-10` | L | partial | ui | Must-Haves card lacks header and per-item icons / card styling | Present Must-Haves as a bordered card with a priority_high header icon and a green check_circle before each item; the implementation renders a plain bulleted list with no icons. |
| `04-jd-pipeline-tailoring-11` | L | partial | ui | Artifact tab icons missing | Add leading Material icons to the artifact tabs ('description' Tailored CV, 'mail' Cover Letter); tabs are text-only. |
| `04-jd-pipeline-tailoring-12` | L | partial | interaction | 'Drift Check Active' is a static label, not an interactive button | Render 'Drift Check Active' as a bordered, hover-able button with a 'rule' icon linking to drift checking; the implementation shows a non-interactive span badge. |

## 05-drift-check-diagnostics

_Implementation is a single-package, vertically stacked diagnostics view; the design is a multi-document master/detail history dashboard. Aggregate metric cards, the Recent Checks list, the detail stat-row, the Export button, and the side-by-side Semantic Trace Diff viewer are all absent._

| ID | Sev | Status | Cat | Feature | What's needed |
|---|---|---|---|---|---|
| `05-drift-check-diagnostics-1` | H | missing | flow | History/aggregate framing missing (single-package only) | Make this a 'Drift Checks History' page reviewing quality assessments for all tailored documents with a master/detail layout; the implementation is a single-package detail page keyed on a route slug with no cross-document history concept. |
| `05-drift-check-diagnostics-2` | H | missing | data | Bento-grid summary metric cards absent | Add the top 4-card metrics row (Total Checks 142, Avg Content Loss 0.02% green, Fabrication Alerts 3 error, Avg Keyword Match 87%) each with icon and uppercase label. |
| `05-drift-check-diagnostics-3` | H | missing | ui | Recent Checks master list panel absent | Add the left (lg:col-span-4) scrollable 'Recent Checks' history list with selectable items; the implementation only stacks the current package's sections with no way to browse between checks. |
| `05-drift-check-diagnostics-4` | H | missing | ui | Semantic Trace Diff split-pane viewer missing | Add the two-column 'Semantic Trace Diff' viewer (left canonical source, right tailored output, monospace, paragraph-aligned); the implementation lists unsourced-claim cards with no canonical-vs-tailored comparison. |
| `05-drift-check-diagnostics-5` | H | missing | ui | Color-coded diff highlighting (removals/additions) missing | Highlight canonical removals (red background + strikethrough) and tailored additions (green background + bold inserted text) as a literal diff; no such styling exists. |
| `05-drift-check-diagnostics-6` | M | missing | ui | History list-item status chips and relative timestamps missing | Each history item should show job title, relative timestamp, a color-coded loss/fabrication chip, a 'Match: X%' chip, and an active-selection highlight; none exist. |
| `05-drift-check-diagnostics-7` | M | missing | interaction | Filter control on Recent Checks missing | Add the filter button (filter_list icon) in the Recent Checks header; no filter/sort affordance exists. |
| `05-drift-check-diagnostics-8` | M | missing | data | Detail header Check ID and run-timestamp metadata missing | Show the document title plus 'Check ID: #DC-84920 • Run: Oct 24, 2023, 14:32 PST' in the detail header; only a breadcrumb and slug are shown despite ran_at being available. |
| `05-drift-check-diagnostics-9` | M | missing | interaction | Export Report button missing | Add the bordered 'Export Report' button (download icon) to the detail header; no export/download action exists on the drift page. |
| `05-drift-check-diagnostics-10` | M | partial | ui | Consolidated three-metric stat row in detail header missing | Add the horizontal stat strip ('Fabrication Score 0.0 (Perfect)', 'Content Loss 0%', 'Keyword Density 92% Match') with vertical dividers; the implementation surfaces only per-section badges with no numeric score or keyword-density percentage. |
| `05-drift-check-diagnostics-11` | L | missing | content | Diff legend missing | Add the diff legend with a red 'Canonical Removal' swatch and a green 'Tailored Addition' swatch. |
| `05-drift-check-diagnostics-12` | L | missing | content | Source/output artifact filename labels missing | Label each diff pane with a chip naming the artifact ('Source: master_cv.yaml', 'Output: stripe_tailored.md'); the implementation shows paths only inside individual claim cards. |
