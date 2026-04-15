# CLI Reference

Shipyard exposes five commands through the `shipyard` entry point.

```
shipyard --help
```

---

## `shipyard init`

Set up the Shipyard epic-driver workflow in a repository.

**Purpose:** Copies the bundled `epic-driver.yml` template into `.github/workflows/` and substitutes `SHIPYARD_VERSION` with the installed package version.

**Arguments and flags:**

| Name | Type | Description |
|------|------|-------------|
| `PATH` | positional argument | Target repository directory (default: `.`) |
| `--force` | flag | Overwrite an existing `epic-driver.yml` |

**Outputs:** Creates `.github/workflows/epic-driver.yml` in the target directory.

**Example:**

```bash
# Scaffold workflow in the current repo
shipyard init

# Scaffold into a different repo directory
shipyard init ../my-other-repo

# Overwrite an existing workflow
shipyard init --force
```

After running, add `CLAUDE_CODE_OAUTH_TOKEN` as a secret in the target repository's settings.

---

## `shipyard tasks`

Parse a markdown plan into task JSON.

**Purpose:** Reads a plan written in the shipyard markdown format, validates dependencies, and emits a `tasks.json` file (or JSON to stdout) suitable for `shipyard sync`.

**Flags:**

| Flag | Description |
|------|-------------|
| `-i`, `--input FILE` | Input markdown file (default: stdin) |
| `-o`, `--output FILE` | Output JSON file (default: stdout) |

**Inputs:** A markdown plan file. See [task-format.md](task-format.md) for the exact syntax.

**Outputs:** A JSON object with `title`, `body`, and `tasks[]`. See [task-format.md](task-format.md) for the schema.

**Example:**

```bash
# Parse to file
shipyard tasks -i plan.md -o tasks.json

# Parse from stdin, inspect on stdout
cat plan.md | shipyard tasks | jq '.tasks | length'
```

Exits non-zero if dependency references are invalid (e.g., a task depends on a non-existent task ID).

---

## `shipyard sync`

Sync task JSON to GitHub Issues.

**Purpose:** Creates the epic issue, one sub-issue per task, links them via the GitHub sub-issues API, wires `blocked-by` dependency edges, and applies the `in-progress` label to the epic.

**Flags:**

| Flag | Description |
|------|-------------|
| `-i`, `--input FILE` | Input `tasks.json` (default: stdin) |
| `--repo OWNER/REPO` | Target repository (default: auto-detected via `gh repo view`) |
| `--dry-run` | Print all planned API calls without executing them |

**Inputs:** The JSON produced by `shipyard tasks`.

**Outputs:** Prints progress to stdout. On success, prints URLs for the epic and each task issue.

**Example:**

```bash
# Sync to current repo
shipyard sync -i tasks.json

# Sync to a specific repo
shipyard sync -i tasks.json --repo myorg/myrepo

# Preview without creating issues
shipyard sync -i tasks.json --dry-run
```

Requires `gh` CLI to be authenticated. Exits with code 1 on partial failures (some issues may still have been created).

---

## `shipyard find-work` (CI only)

Find unblocked sub-issues for the current epic.

**Purpose:** Resolves the active epic from the trigger event, queries GitHub for open sub-issues with no open blockers, and writes a JSON payload to `$GITHUB_OUTPUT`. Called by the `find-work` job in `epic-driver.yml`.

**Configuration:** Entirely via environment variables (set by the workflow):

| Variable | Description |
|----------|-------------|
| `GITHUB_REPOSITORY` | `owner/repo` (set automatically by Actions) |
| `EVENT_NAME` | `issues`, `pull_request`, or `workflow_dispatch` |
| `ISSUE_NUMBER` | Epic issue number (required for `issues`/`workflow_dispatch`) |
| `PR_BODY` | PR body text (used when `EVENT_NAME=pull_request`) |

**Outputs (to `$GITHUB_OUTPUT`):**

| Key | Value |
|-----|-------|
| `has_work` | `"true"` or `"false"` |
| `work_json` | JSON payload for `shipyard execute` (only when `has_work=true`) |

**Not intended for direct use outside CI.** See [github-integration.md](github-integration.md) for epic resolution details.

---

## `shipyard execute` (CI only)

Run the three-agent pipeline for unblocked issues.

**Purpose:** Reads the work payload from `$WORK_JSON`, creates a feature branch, and runs the implementer → spec reviewer → code quality reviewer pipeline for each issue. On success, pushes the branch and opens a PR. Called by the `execute` job in `epic-driver.yml`.

**Configuration:** Entirely via environment variables:

| Variable | Description |
|----------|-------------|
| `WORK_JSON` | JSON payload from `shipyard find-work` |
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for Claude Code agents |
| `GITHUB_RUN_ID` | Used to name the feature branch (falls back to current epoch seconds if unset) |

**Outputs:**

- Creates and pushes a branch named `shipyard/epic-<N>-run-<RUN_ID>`
- Opens a PR against `main` titled `shipyard: implement N issue(s) from epic #N`
- Posts a comment on each failed issue explaining why it was skipped

> **Note:** The PR base branch is hardcoded to `main`. Repositories whose default branch has a different name must edit the workflow's `execute` step accordingly.

**Not intended for direct use outside CI.** See [agent-pipeline.md](agent-pipeline.md) for pipeline details.
