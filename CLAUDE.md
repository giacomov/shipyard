# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

Detailed documentation lives in `docs/`. Before making changes, read the relevant doc:

| Doc | Covers |
|-----|--------|
| `docs/ARCHITECTURE.md` | Component diagram, data flow, package layout |
| `docs/cli.md` | All five CLI commands with flags and examples |
| `docs/agent-pipeline.md` | Three-agent pipeline, retry logic, failure handling |
| `docs/task-format.md` | Markdown plan syntax, JSON schemas |
| `docs/github-integration.md` | Issues, sub-issues, blocked-by, labels, permissions |
| `docs/workflow.md` | `epic-driver.yml` jobs, secrets, data flow between jobs |
| `docs/agent-prompts.md` | Prompt files, placeholder substitution, customization |

## Commands

```bash
# Install for development (creates .venv automatically)
uv sync --extra dev

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_commands_sync.py

# Run a single test by name
uv run pytest tests/test_commands_sync.py::test_run_sync_dry_run

# Run the CLI (after install)
uv run shipyard --help

# Lint and format manually
uv run ruff check --fix .
uv run ruff format .
```

Use type hints on all functions and methods (Python 3.13+ syntax is fine — e.g. `X | Y`, `list[str]`, `dict[str, int]`).

## Dependency management

This project uses **uv** for dependency management with **setuptools** as the build backend.

**Rules for keeping `pyproject.toml` and `uv.lock` in sync:**

- All dependencies in `pyproject.toml` (both `[project.dependencies]` and `[project.optional-dependencies]`) must be pinned to an exact patch version (e.g. `click==8.2.1`, not `click>=8.0`).
- After adding, removing, or changing any dependency version in `pyproject.toml`, always run `uv lock` to regenerate `uv.lock`. Both files must be committed together.
- To add a new dependency: add the pinned version to `pyproject.toml`, run `uv lock`, then `uv sync --extra dev`.
- To upgrade a dependency: update the pinned version in `pyproject.toml`, run `uv lock`, then `uv sync --extra dev`.
- Never edit `uv.lock` by hand — it is always generated from `pyproject.toml` via `uv lock`.
- The `.python-version` file pins the interpreter to `3.13.2`; do not change it without also updating `requires-python` in `pyproject.toml`.

## Pre-commit hooks

A pre-commit hook runs `ruff` (lint + autofix) and `ruff format` on every commit. The hook is installed at `.git/hooks/pre-commit` via:

```bash
uv run pre-commit install
```

If the hook is missing (e.g. after a fresh clone), run the above command once. The hook config lives in `.pre-commit-config.yaml`.

## Architecture

Shipyard is a CLI tool + bundled GitHub Actions workflow that turns a markdown implementation plan into an autonomous agent pipeline on GitHub Actions.

### The two-phase model

**Local phase (developer machine):**
1. `shipyard tasks` parses a markdown plan (`### Task N:` blocks with `**Depends on:**` lines) into `tasks.json`.
2. `shipyard sync` creates GitHub Issues from that JSON: one epic issue, one sub-issue per task, sub-issue links, `blocked-by` dependency edges, and the `in-progress` label on the epic.

**CI phase (GitHub Actions, triggered by label/PR/dispatch):**
1. `find-work` job: `shipyard find-work` reads event context from env vars, resolves the active epic, fetches open sub-issues, filters to those with no open blockers, and writes a `work_json` payload to `$GITHUB_OUTPUT`.
2. `execute` job: `shipyard execute` reads `$WORK_JSON`, creates a feature branch, and runs a **three-agent pipeline** (implementer → spec reviewer → code quality reviewer) for each unblocked issue sequentially. On success it pushes the branch and opens a PR against `main`.

### Package layout

```
shipyard/
  cli.py               # Click group wiring all five commands
  commands/
    init.py            # copies bundled epic-driver.yml template into .github/workflows/
    tasks.py           # markdown → ParsedPlan → tasks.json (pure parsing, no I/O side effects)
    sync.py            # tasks.json → GitHub Issues via gh CLI subprocess calls
    find_work.py       # epic resolution + unblocked sub-issue lookup; writes $GITHUB_OUTPUT
    execute.py         # async three-agent pipeline using claude-agent-sdk
  prompts/             # plain-text prompt templates with {PLACEHOLDER} tokens
  templates/           # epic-driver.yml with SHIPYARD_VERSION placeholder
```

### Agent pipeline (`execute.py`)

- Uses `claude_agent_sdk.query()` (async generator) with `bypassPermissions` mode and tools `Bash, Read, Write, Edit, Glob, Grep`.
- For each issue: records `base_sha`, runs implementer → parses `ImplementerStatus` from the last lines of output → runs spec reviewer → runs code quality reviewer. Both reviewers must return `APPROVED` (verdict parsed by `parse_review_verdict()`).
- On review failure with retries remaining: `git reset --hard base_sha` and re-run implementer with the reviewer feedback injected into `{CONTEXT}`.
- On terminal failure: reset, post a GitHub Issue comment with `<!-- shipyard-executor: REASON -->` tag, continue to next issue.
- `max_retries=1` → up to 2 total attempts per issue.

### GitHub data model

GitHub Issues are the only persistent store — no database. The epic issue is the root node; sub-issues are tasks; `blocked-by` edges encode dependencies. `find-work` reads this graph at runtime to determine what to run next.

### Key design constraints

- `find_work.py` and `execute.py` are CI-only (driven entirely by env vars, no Click options).
- All GitHub API calls in `sync.py` and `find_work.py` go through the `gh` CLI as subprocesses.
- The bundled `epic-driver.yml` template uses `SHIPYARD_VERSION` as a placeholder; `shipyard init` substitutes it with `importlib.metadata.version("shipyard")`.
- PRs are always opened against `main` (hardcoded in `execute.py:create_pull_request`).
