# Shipyard CLI Design

**Date:** 2026-04-14
**Status:** Approved

## Overview

Convert Shipyard from a collection of standalone scripts into an installable Python CLI (`shipyard`) that users run locally to set up and drive the agentic GitHub Actions pipeline. The scripts move into a proper `shipyard/` package; a bundled workflow template is copied into user repos via `shipyard init`.

## Package Structure

```
shipyard/
  __init__.py
  cli.py                  # click group entry point
  commands/
    __init__.py
    init.py               # shipyard init
    tasks.py              # shipyard tasks   (was plan_to_tasks.py)
    sync.py               # shipyard sync    (was sync_to_github.py)
    find_work.py          # shipyard find-work  (was find_epic_work.py)
    execute.py            # shipyard execute    (was executor.py)
  templates/
    epic-driver.yml       # bundled workflow template
scripts/                  # deleted
```

`cli.py` is a thin click group that imports and registers each command:

```python
@click.group()
def main(): pass

main.add_command(init)
main.add_command(tasks)
main.add_command(sync)
main.add_command(find_work, name="find-work")
main.add_command(execute)
```

## Commands

### Local commands (user-facing)

**`shipyard init [PATH]`**
- Copies `shipyard/templates/epic-driver.yml` to `PATH/.github/workflows/epic-driver.yml`
- `PATH` defaults to `.`
- Pins the installed version of shipyard in the copied workflow (`pip install shipyard==X.Y.Z`)
- Errors if the file already exists; `--force` overwrites
- Options: `--force`

**`shipyard tasks`**
- Parses a superpowers-style markdown plan into structured task JSON with dependency tracking
- Options: `-i/--input FILE` (default: stdin), `-o/--output FILE` (default: stdout)
- Logic from: `plan_to_tasks.py`

**`shipyard sync`**
- Pushes task JSON to GitHub: creates an epic issue, sub-issues, and blocked-by relationships
- Options: `-i/--input FILE` (default: stdin), `--repo REPO` (default: inferred from `gh`), `--dry-run`
- Logic from: `sync_to_github.py`

### CI commands (GitHub Actions only)

**`shipyard find-work`**
- Finds the current in-progress epic and its unblocked sub-issues
- No CLI flags — all config via env vars set by GitHub Actions:
  - `GITHUB_REPOSITORY`, `EVENT_NAME`, `ISSUE_NUMBER`, `PR_BODY`, `GH_TOKEN`, `GITHUB_OUTPUT`
- Logic from: `find_epic_work.py`

**`shipyard execute`**
- Runs the three-agent pipeline (implementer → spec reviewer → code quality reviewer) for each unblocked issue
- No CLI flags — all config via env vars:
  - `WORK_JSON`, `CLAUDE_CODE_OAUTH_TOKEN`, `GH_TOKEN`, `GITHUB_RUN_ID`
- Logic from: `executor.py`

## Workflow Template

`shipyard/templates/epic-driver.yml` is the workflow copied to user repos. Key differences from the current shipyard repo workflow:

1. **`find-work` job drops `actions/checkout`** — not needed since scripts install via pip
2. **Script invocations become CLI commands** — `python scripts/find_epic_work.py` → `shipyard find-work`
3. **Version-pinned install** — `pip install shipyard==X.Y.Z` (version substituted by `shipyard init`)

The shipyard repo's own `.github/workflows/epic-driver.yml` remains separate (dogfood workflow using `pip install -e .`).

## Dependencies

Add `click` to `[project.dependencies]` in `pyproject.toml`.

Update `pyproject.toml`:

```toml
[project.scripts]
shipyard = "shipyard.cli:main"

[tool.setuptools.packages.find]
include = ["shipyard*"]          # was "scripts*"

[tool.setuptools.package-data]
shipyard = ["templates/*.yml"]
```

## Tests

- Update all imports: `from scripts.X import Y` → `from shipyard.commands.X import Y`
- Replace current `test_scaffolding.py` with checks for the new package structure (entry point, template file present)
- Add click `CliRunner`-based tests for each command module
- `test_workflow.py` tests the bundled template (`shipyard/templates/epic-driver.yml`) instead of `.github/workflows/epic-driver.yml`
- No logic changes to existing unit tests — only import path updates

## Installation

```bash
# From PyPI (when public)
pip install shipyard

# From git (private or pre-release)
pip install git+https://github.com/owner/shipyard.git

# Editable (development)
pip install -e .
```

## User Setup Flow

```bash
pip install shipyard
shipyard init .
# → creates .github/workflows/epic-driver.yml
# → add CLAUDE_CODE_OAUTH_TOKEN secret in GitHub repo settings
```
