# CLI Reference

Shipyard exposes seven commands through the `shipyard` entry point.

```
shipyard --help
```

---

## `shipyard init`

Set up the Shipyard workflows in a repository.

**Purpose:** Copies the bundled `epic-driver.yml` and `plan-driver.yml` templates into `.github/workflows/` and substitutes `SHIPYARD_VERSION` with the installed package version (or `main` when `--from-main` is set).

**Arguments and flags:**

| Name | Type | Description |
|------|------|-------------|
| `PATH` | positional argument | Target repository directory (default: `.`) |
| `--force` | flag | Overwrite existing workflow files |
| `--skip-plan-driver` | flag | Only install `epic-driver.yml`, skip `plan-driver.yml` |
| `--from-main` | flag | Install shipyard from HEAD of `main` instead of the pinned version |

**Outputs:** Creates `.github/workflows/epic-driver.yml` (and `plan-driver.yml` unless skipped) in the target directory.

**Example:**

```bash
# Scaffold both workflows in the current repo
shipyard init

# Scaffold into a different repo directory
shipyard init ../my-other-repo

# Overwrite existing workflows
shipyard init --force

# Install from main branch (useful before tagging a release)
shipyard init --from-main

# Only install the epic driver
shipyard init --skip-plan-driver
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

## `shipyard plan` (CI only)

Generate or update an implementation plan for a GitHub issue.

**Purpose:** Runs a planning agent to produce a structured markdown implementation plan, writing it to `plans/i<issue-number>.md`. Called by the `plan` job in `plan-driver.yml`. Does not perform any git or GitHub operations — those are handled by the surrounding workflow steps.

**Configuration:**

| Flag | Description |
|------|-------------|
| `--prompt TEXT` | Inline planning context |
| `--prompt-file FILE` | File containing planning context |
| `--issue-number TEXT` | Issue number (used to name the output file, default: `local-test`) |
| `--issue-title TEXT` | Issue title (passed through to the workflow for PR creation) |
| `--pr-number INT` | PR number — triggers re-planning mode |
| `--existing-plan-path FILE` | Existing plan file to revise (re-planning only) |
| `--review-feedback-file FILE` | File containing review feedback to incorporate (re-planning only) |

One of `--prompt` or `--prompt-file` is required.

**Outputs:**

- Writes `plans/i<issue-number>.md` (creates the `plans/` directory if needed).
- Prints the plan file path to stdout.

**Modes:**

- **Initial plan** (no `--pr-number`): generates a plan from scratch given the issue context.
- **Re-plan** (`--pr-number` set): revises an existing plan incorporating review feedback.

**Example:**

```bash
# Generate a plan locally
shipyard plan --prompt "Add a rate limiter to the API" --issue-number 42

# Re-plan with review feedback
shipyard plan \
  --pr-number 99 \
  --prompt-file prompt.txt \
  --issue-number 42 \
  --existing-plan-path plans/i42.md \
  --review-feedback-file feedback.txt
```

**Not intended for direct use outside CI** (the workflow handles git checkout, commit, and PR creation around it). Can be run locally to test the planning agent without side effects.

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

**Purpose:** Reads the work payload from `$WORK_JSON` and runs the implementer → spec reviewer → code quality reviewer pipeline for each issue sequentially. Writes results to `shipyard-results.json` for the subsequent `publish-execution` step. Called by the `execute` job in `epic-driver.yml`.

**Configuration:** Entirely via environment variables:

| Variable | Description |
|----------|-------------|
| `WORK_JSON` | JSON payload from `shipyard find-work` |
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for Claude Code agents |

**Outputs:**

- Writes `shipyard-results.json` with `{ "successful": [<issue numbers>], "failed": [<issue numbers>] }`.
- Posts a comment on each failed issue explaining why it was skipped.
- Exits non-zero if any issues failed.

Does **not** create a branch, push, or open a PR — that is handled by `shipyard publish-execution`.

**Not intended for direct use outside CI.** See [agent-pipeline.md](agent-pipeline.md) for pipeline details.

---

## `shipyard publish-execution` (CI only)

Push the implementation branch and open a pull request.

**Purpose:** Reads `shipyard-results.json` written by `shipyard execute`, pushes the branch, and opens a PR against `main` that closes all successfully-implemented issues. Skips silently if no issues succeeded. Called as the final step of the `execute` job in `epic-driver.yml`, with `if: always()` so it runs even if `shipyard execute` exits non-zero.

**Flags:**

| Flag | Description |
|------|-------------|
| `--branch TEXT` | Branch to push (required) |
| `--results-file FILE` | Path to results JSON (default: `shipyard-results.json`) |

**Configuration:** Also reads `$WORK_JSON` for repo and epic metadata.

**Outputs:**

- Pushes the branch to origin.
- Opens a PR titled `shipyard: implement N issue(s) from epic #<N>` with `Closes #<n>` lines for each successful issue.
- Prints the PR URL to stdout.

> **Note:** The PR base branch is hardcoded to `main`. Repositories whose default branch has a different name must edit the workflow's `publish-execution` step accordingly.

**Not intended for direct use outside CI.**
