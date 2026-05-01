# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

Detailed documentation lives in `docs/`. Before making changes, read the relevant doc:

| Doc | Covers |
|-----|--------|
| `ARCHITECTURE.md` | Problem, component overview, codemap, invariants |
| `docs/reference/cli.md` | All nine CLI commands with flags and examples |
| `docs/explanation/agent-pipeline.md` | Three-agent pipeline, retry logic, failure handling |
| `docs/reference/task-format.md` | Markdown plan syntax, JSON schemas |
| `docs/explanation/github-integration.md` | Issues, sub-issues, blocked-by, epic resolution, permissions |
| `docs/reference/workflow.md` | `epic-driver.yml`, `plan-driver.yml`, `sync-driver.yml` jobs, secrets, data flow |
| `docs/reference/agent-prompts.md` | Prompt files, placeholder substitution, customization |

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
1. `shipyard tasks` extracts tasks from a markdown plan into `tasks.json` using an AI agent.
2. `shipyard sync` creates GitHub Issues from that JSON: one epic issue, one sub-issue per task, sub-issue links, and `blocked-by` dependency edges. Also creates and pushes the `shipyard/epic-<N>` branch used as the base for implementation PRs.

**CI phase (GitHub Actions, triggered by PR merge or manual dispatch):**
1. `find-work` job: `shipyard find-work` reads event context from env vars, resolves the active epic, fetches open sub-issues, filters to those with no open blockers, and writes a `work_json` payload to `$GITHUB_OUTPUT`.
2. `execute` job (three steps):
   - Creates the feature branch (`shipyard/epic-<N>-run-<RUN_ID>`).
   - `shipyard execute` reads `/tmp/work.json` and runs a **three-agent pipeline** (implementer → spec reviewer → code quality reviewer) for each unblocked issue sequentially. Writes `shipyard-results.json`.
   - `shipyard publish-execution` pushes the branch and opens a PR against the epic branch (runs with `if: always()` so partial results are always published).

### Package layout

```
shipyard/
  cli.py               # Click group wiring all commands
  commands/
    init.py            # copies bundled workflow templates into .github/workflows/
    tasks.py           # shipyard tasks — AI agent extracts tasks from a plan; writes tasks.json
    sync.py            # tasks.json → GitHub Issues via gh CLI subprocess calls
    find_work.py       # epic resolution + unblocked sub-issue lookup; writes $GITHUB_OUTPUT
    execute.py         # async three-agent pipeline; writes shipyard-results.json
    plan.py            # planning agent runner; writes plans/i<N>.md
    publish.py         # push branch + open PR; reads shipyard-results.json
    update_docs.py     # doc agent + verifier loop; CI use only
  data/
    prompts/           # system-prompt.md — system prompt injected into every agent session
    skills/            # bundled Claude Code skills
    templates/         # epic-driver.yml, plan-driver.yml, and sync-driver.yml with SHIPYARD_VERSION placeholder
  utils/
    git.py             # git subprocess wrappers
    gh.py              # gh CLI wrappers + GitHub output helpers
    github_event.py    # extract-github-event command + event parsing helpers
    agent.py           # get_sdk_client, SimSDKClient, and receive_from_client helpers
```

### Agent pipeline (`execute.py`)

- Uses `ClaudeSDKClient` with `dontAsk` permission mode and tools `Bash, Read, Write, Edit, Glob, Grep, Agent, Monitor`.
- For each issue: records `base_sha`, then drives a single session with sequential `query()` calls: implement → commit → invoke spec reviewer sub-agent (fix & retry within session until approved) → invoke code quality reviewer sub-agent (fix & retry within session until approved) → run tests.
- Spec reviewer and code quality reviewer are registered as named `AgentDefinition` sub-agents that the implementer invokes via the `Agent` tool.
- On terminal failure (exception): `git reset --hard base_sha`, continue to next issue.
- `reset_fn` is an injectable callback (defaults to a no-op), making the pipeline testable without live git state.

### GitHub data model

GitHub Issues are the only persistent store — no database. The epic issue is the root node; sub-issues are tasks; `blocked-by` edges encode dependencies. `find-work` reads this graph at runtime to determine what to run next.

### Key design constraints

- `find_work.py`, `execute.py`, and `publish.py` are CI-only (driven entirely by env vars, no interactive options).
- All GitHub API calls in `sync.py` and `find_work.py` go through the `gh` CLI as subprocesses.
- The bundled workflow templates use `SHIPYARD_VERSION` as a placeholder; `shipyard init` substitutes it with the package version (or the given branch when `--dev BRANCH` is passed).
- PRs are opened against the epic base branch passed via `--base-branch` to `shipyard publish-execution` (default: `settings.pr_base_branch`, which is `main`).
