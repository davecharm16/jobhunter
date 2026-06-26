// Job Scan — Discovery Engine (F2 scan engine workflow), n8n Workflow SDK source.
//
// Live (draft) in n8n: workflow id lFU4bsgLyUO4Evxj
//   https://n8n-production-45e3.up.railway.app/workflow/lFU4bsgLyUO4Evxj
//
// Flow: Cron (daily 08:00) + manual Webhook (POST /webhook/scan-run) → GET
// settings → IF enabled → GET known-urls → GET canonical-profile → Build Scan
// Inputs (base64 JSON) → Execute Command (/opt/scan/run-scan.sh = headless
// Claude + Playwright MCP) → Parse Scan Result → POST /api/scan/results.
//
// Requires these env vars on the n8n service (Task 4): APP_BASE_URL,
// INGEST_SHARED_TOKEN, CLAUDE_CODE_OAUTH_TOKEN (NOT ANTHROPIC_API_KEY).
// HTTP auth is via Authorization: Bearer {{ $env.INGEST_SHARED_TOKEN }} headers
// — no stored n8n credentials needed.
//
// Regenerate / update in n8n with the n8n-mcp (validate_workflow then
// update/create). This file is the source of truth.

import { workflow, node, trigger, ifElse, expr } from '@n8n/workflow-sdk';

const scheduleTrigger = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.3,
  config: {
    name: 'Daily 08:00 Trigger',
    parameters: { rule: { interval: [{ field: 'days', daysInterval: 1, triggerAtHour: 8, triggerAtMinute: 0 }] } },
  },
  output: [{}],
});

const manualWebhook = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Manual Run Webhook',
    parameters: { httpMethod: 'POST', path: 'scan-run', responseMode: 'onReceived' },
  },
  output: [{ body: { trigger: 'manual' } }],
});

const getSettings = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Settings',
    parameters: {
      method: 'GET',
      url: expr('{{ $env.APP_BASE_URL }}/api/scan/settings'),
      sendHeaders: true,
      specifyHeaders: 'keypair',
      headerParameters: { parameters: [{ name: 'Authorization', value: expr('Bearer {{ $env.INGEST_SHARED_TOKEN }}') }] },
    },
  },
  output: [{ search_titles: ['Solutions Architect'], sites_enabled: ['indeed', 'linkedin'], picks_per_site: 3, enabled: true }],
});

const checkEnabled = ifElse({
  version: 2.2,
  config: {
    name: 'Scanning Enabled?',
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' },
        conditions: [{ leftValue: expr('{{ $json.enabled }}'), operator: { type: 'boolean', operation: 'true', singleValue: true } }],
        combinator: 'and',
      },
    },
  },
});

const getKnownUrls = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Known URLs',
    parameters: {
      method: 'GET',
      url: expr('{{ $env.APP_BASE_URL }}/api/scan/known-urls'),
      sendHeaders: true,
      specifyHeaders: 'keypair',
      headerParameters: { parameters: [{ name: 'Authorization', value: expr('Bearer {{ $env.INGEST_SHARED_TOKEN }}') }] },
    },
  },
  output: [{ urls: ['https://jobs.example.com/known-1'] }],
});

const getProfile = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Canonical Profile',
    parameters: {
      method: 'GET',
      url: expr('{{ $env.APP_BASE_URL }}/api/canonical-profile'),
      sendHeaders: true,
      specifyHeaders: 'keypair',
      headerParameters: { parameters: [{ name: 'Authorization', value: expr('Bearer {{ $env.INGEST_SHARED_TOKEN }}') }] },
    },
  },
  output: [{ name: 'Dave', label: 'Solutions Designer', summary: 'Builds things.', skills: ['Mobile'], recent_titles: ['Solutions Designer @ Stratpoint'] }],
});

const buildInputs = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Scan Inputs',
    parameters: {
      mode: 'runOnceForAllItems',
      language: 'javaScript',
      jsCode: "const settings = $('Get Settings').item.json;\nconst knownUrls = $('Get Known URLs').item.json.urls || [];\nconst profile = $('Get Canonical Profile').item.json;\nconst inputs = {\n  search_titles: settings.search_titles || [],\n  sites_enabled: settings.sites_enabled || [],\n  picks_per_site: settings.picks_per_site || 3,\n  canonical_profile: profile,\n  known_urls: knownUrls,\n};\nconst inputsB64 = Buffer.from(JSON.stringify(inputs)).toString('base64');\nreturn [{ json: { inputsB64 } }];",
    },
  },
  output: [{ inputsB64: 'eyJzZWFyY2hfdGl0bGVzIjpbXX0=' }],
});

const runScan = node({
  type: 'n8n-nodes-base.executeCommand',
  version: 1,
  config: {
    name: 'Run Claude Scan',
    parameters: {
      executeOnce: true,
      command: expr("echo '{{ $json.inputsB64 }}' | /opt/scan/run-scan.sh"),
    },
  },
  output: [{ exitCode: 0, stdout: '{"type":"result","result":"{}"}', stderr: '' }],
});

const parseResult = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Parse Scan Result',
    parameters: {
      mode: 'runOnceForAllItems',
      language: 'javaScript',
      jsCode: "const raw = $json.stdout || '';\nlet envelope;\ntry { envelope = JSON.parse(raw); } catch (e) { throw new Error('claude stdout was not JSON: ' + raw.slice(0, 500)); }\nlet inner = envelope.result !== undefined ? envelope.result : envelope;\nif (typeof inner === 'string') {\n  let s = inner.trim();\n  if (s.startsWith('```')) { s = s.replace(/^```[a-zA-Z]*\\n?/, '').replace(/```$/, '').trim(); }\n  try { inner = JSON.parse(s); } catch (e) { throw new Error('agent result was not JSON: ' + s.slice(0, 500)); }\n}\nif (!inner || !Array.isArray(inner.candidates)) { throw new Error('scan result missing candidates[]'); }\nreturn [{ json: inner }];",
    },
  },
  output: [{ site_summary: { indeed: { status: 'ok', count: 1 } }, candidates: [{ site: 'indeed', url: 'https://jobs.example.com/1', title: 'Dev', jd_text: 'JD' }] }],
});

const postResults = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Post Results to App',
    parameters: {
      method: 'POST',
      url: expr('{{ $env.APP_BASE_URL }}/api/scan/results'),
      sendHeaders: true,
      specifyHeaders: 'keypair',
      headerParameters: { parameters: [{ name: 'Authorization', value: expr('Bearer {{ $env.INGEST_SHARED_TOKEN }}') }] },
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: expr('{{ JSON.stringify($json) }}'),
    },
  },
  output: [{ scan_id: 'uuid', received: 1, new: 1, skipped: 0 }],
});

export default workflow('job-scan-engine', 'Job Scan — Discovery Engine')
  .add(scheduleTrigger)
  .to(getSettings)
  .to(checkEnabled.onTrue(
    getKnownUrls.to(getProfile).to(buildInputs).to(runScan).to(parseResult).to(postResults)
  ))
  .add(manualWebhook)
  .to(getSettings);
