---
stateFile: "/Users/davecharmbulaquena/Desktop/job_hunter/_bmad-output/story-automator/orchestration-1-20260522-181652.md"
createdAt: "2026-05-22T18:17:39Z"
---

# Agents Plan: Job Hunter - Epic Breakdown

```json
{
  "version": "1.0.0",
  "stateFile": "/Users/davecharmbulaquena/Desktop/job_hunter/_bmad-output/story-automator/orchestration-1-20260522-181652.md",
  "epic": "1",
  "epicName": "Job Hunter - Epic Breakdown",
  "createdAt": "2026-05-22T18:17:39Z",
  "stories": [
    {
      "storyId": "1.1",
      "title": "Runtime, language, and canonical-CV schema bootstrap",
      "complexity": "low",
      "tasks": {
        "create": {
          "primary": "claude",
          "fallback": false
        },
        "dev": {
          "primary": "claude",
          "fallback": false
        },
        "auto": {
          "primary": "claude",
          "fallback": false
        },
        "review": {
          "primary": "claude",
          "fallback": false
        }
      }
    },
    {
      "storyId": "1.2",
      "title": "CLI scaffold, `.env` secrets handling, and cost-cap config",
      "complexity": "medium",
      "tasks": {
        "create": {
          "primary": "codex",
          "fallback": "claude"
        },
        "dev": {
          "primary": "codex",
          "fallback": "claude"
        },
        "auto": {
          "primary": "codex",
          "fallback": "claude"
        },
        "review": {
          "primary": "codex",
          "fallback": "claude"
        }
      }
    },
    {
      "storyId": "1.3",
      "title": "Canonical CV reader with PDF/docx ingest rejection",
      "complexity": "medium",
      "tasks": {
        "create": {
          "primary": "codex",
          "fallback": "claude"
        },
        "dev": {
          "primary": "codex",
          "fallback": "claude"
        },
        "auto": {
          "primary": "codex",
          "fallback": "claude"
        },
        "review": {
          "primary": "codex",
          "fallback": "claude"
        }
      }
    },
    {
      "storyId": "1.4",
      "title": "`jobhunter paste` JD ingest from stdin or file argument",
      "complexity": "medium",
      "tasks": {
        "create": {
          "primary": "codex",
          "fallback": "claude"
        },
        "dev": {
          "primary": "codex",
          "fallback": "claude"
        },
        "auto": {
          "primary": "codex",
          "fallback": "claude"
        },
        "review": {
          "primary": "codex",
          "fallback": "claude"
        }
      }
    },
    {
      "storyId": "1.5",
      "title": "Single tailoring LLM call writes tailored CV + cover letter to `./out/<slug>/`",
      "complexity": "medium",
      "tasks": {
        "create": {
          "primary": "codex",
          "fallback": "claude"
        },
        "dev": {
          "primary": "codex",
          "fallback": "claude"
        },
        "auto": {
          "primary": "codex",
          "fallback": "claude"
        },
        "review": {
          "primary": "codex",
          "fallback": "claude"
        }
      }
    }
  ]
}
```
