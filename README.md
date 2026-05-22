# jobhunter

Solo-developer pipeline for tailoring a CV + cover letter to a pasted job description, with three downstream drift checks (fabrication, content-loss, keyword-stuffing) that hold any package showing drift instead of publishing it. Runs locally, filesystem-only, no database in v1.

The canonical source of truth for the applicant's profile is a single file in version control (`canonical-cv.json`), validated against the [JSON Resume](https://jsonresume.org) v1.0.0 schema. See [`DECISIONS.md`](./DECISIONS.md) for the foundational runtime + schema decisions.

## Getting started

Requires Python ≥ 3.11.

```bash
# 1. Create and activate a virtualenv.
python3 -m venv .venv
source .venv/bin/activate

# 2. Install in editable mode (pulls in jsonschema and dotenv support).
pip install -e .

# 3. Copy local runtime configuration placeholders and fill in private values.
cp .env.example .env

# 4. Validate the canonical CV against the vendored JSON Resume v1.0.0 schema.
#    Exits 0 on success, non-zero with a human-readable error on failure.
python scripts/validate_canonical_cv.py

# 5. (Optional) Install dev deps and run the test suite.
pip install -e ".[dev]"
pytest
```

The validator reads from the vendored schema at `schemas/jsonresume-v1.0.0.json` and never touches the network — paste mode must keep working offline (PRD NFR13).

## Configuration

Copy `.env.example` to `.env`, then replace the placeholder `LLM_API_KEY` and `MONTHLY_SPEND_CAP_USD` values for your local machine. `.env` and local dotenv variants are ignored by git; keep secrets out of commits.

`jobhunter paste` validates local secrets and the monthly LLM spend cap before any future pipeline work. Job Hunter only writes local files and never submits to Upwork, LinkedIn, OnlineJobs.ph, or any job board.

Hand a job description to the paste pipeline either by piping it to stdin or by passing a saved file:

```bash
# Pipe a JD from your clipboard:
pbpaste | jobhunter paste

# Or pass a saved JD file:
jobhunter paste --file jd-acme-senior-python.txt
```

If both `--file` and a piped stdin are provided in the same invocation, `--file` wins. `jobhunter paste` only holds the JD in memory — no `./out/` directory is created in Story 1.4; tailoring lands in Story 1.5.

The canonical CV must be a text format (JSON Resume v1.0.0 today; markdown or YAML if the fall-back criterion in [`DECISIONS.md`](./DECISIONS.md) §2 fires). `.pdf`, `.docx`, and `.doc` paths are rejected by extension before any read attempt — Job Hunter never parses binary CV formats.

## Repo layout

```
.
├── DECISIONS.md              # foundational decisions (runtime, schema)
├── canonical-cv.json         # canonical CV (JSON Resume v1.0.0)
├── pyproject.toml
├── schemas/
│   └── jsonresume-v1.0.0.json   # vendored — do NOT fetch at runtime
├── scripts/
│   └── validate_canonical_cv.py
├── src/jobhunter/
│   ├── __init__.py
│   ├── cli.py                # argparse CLI scaffold
│   ├── config.py             # CANONICAL_CV_PATH
│   ├── runtime_config.py     # dotenv secrets + monthly cap loader
│   └── canonical_cv.py       # read_canonical_cv() — FR4 single reader
└── tests/
    ├── conftest.py
    ├── unit/                 # config, reader contract, sample-CV shape
    └── integration/          # CLI entry stub, validator script
```

## Status

Stories 1.1–1.4 (walking-skeleton runtime + CLI scaffold + canonical-CV reader hardening + JD ingest via stdin/`--file`) complete. See `_bmad-output/implementation-artifacts/sprint-status.yaml` for sprint progress.
