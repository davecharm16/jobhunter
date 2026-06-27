# Playwright base = Node + Chromium + all browser OS deps preinstalled (Debian).
# We layer n8n + Claude Code CLI + the Playwright MCP on top. This avoids the
# Alpine/Chromium pain of extending the stock n8nio/n8n image.
FROM mcr.microsoft.com/playwright:v1.49.0-jammy

ENV N8N_PORT=5678 \
    NODE_ENV=production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# The Playwright jammy base ships Node 22.11, but n8n REFUSES to start on
# anything below 22.22. Bump Node to a supported 22.x via `n` before installing.
RUN npm install -g n && n 22.22.1 && npm cache clean --force

# n8n, Claude Code CLI, Playwright MCP (global) — installed with the bumped Node
RUN node -v && npm install -g n8n@latest @anthropic-ai/claude-code @playwright/mcp \
    && npm cache clean --force

# Scan assets baked into the image (the workflow references these paths).
RUN mkdir -p /opt/scan
COPY deploy/n8n/mcp.json /opt/scan/mcp.json
COPY deploy/n8n/run-scan.sh /opt/scan/run-scan.sh
COPY prompts/job_scan.v1.md /opt/scan/job_scan.v1.md
RUN chmod +x /opt/scan/run-scan.sh

EXPOSE 5678
CMD ["n8n", "start"]
