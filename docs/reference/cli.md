# CLI reference

Shipyard exposes nine commands through the `shipyard` entry point.

```
shipyard --help
```

---

## `shipyard init`

Set up the Shipyard workflows in a repository.

**Purpose:** Copies the bundled `epic-driver.yml`, `plan-driver.yml`, and `sync-driver.yml` templates into `.github/workflows/` and substitutes `SHIPYARD_VERSION` with the installed package version (or `main` when `--from-main` is set).

**Arguments and flags:**

| Name | Type | Description |
|------|------|-------------|
| `PATH` | positional argument | Target repository directory (default: `.`) |
| `--force` | flag | Overwrite existing workflow files |
| `--skip-plan-driver` | flag | Only install `epic-driver.yml`, skip `plan-driver.yml` and `sync-driver.yml` |
| `--from-main` | flag | Install shipyard from HEAD of `main` instead of the pinned version |

**Outputs:** Creates `.github/workflows/epic-driver.yml`, `plan-driver.yml`, and `sync-driver.yml` (the latter two skipped when `--skip-plan-driver` is set) in the target directory.

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
| `-i`, `--input FILE` | Input markdown file (required) |
| `-t`, `--title TEXT` | Plan title (required) |
| `-o`, `--output FILE` | Output JSON file (default: stdout) |

**Inputs:** A markdown plan file. See [task-format.md](task-format.md) for the exact syntax.

**Outputs:** A JSON object with `title`, `description`, and `tasks[]`. See [task-format.md](task-format.md) for the schema.

**Example:**

```bash
# Parse to file
shipyard tasks -i plan.md -t "My Feature Plan" -o tasks.json

# Parse and inspect on stdout
shipyard tasks -i plan.md -t "My Feature Plan" | jq '.tasks | length'
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
| `--no-in-progress-label` | Skip adding the `in-progress` label to the epic issue |

**Inputs:** The JSON produced by `shipyard tasks`.

**Outputs:** Prints progress to stdout. On success, prints URLs for the epic and each task issue, and creates and pushes the `shipyard/epic-<N>` branch that the CI workflow will use as the base for implementation PRs.

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

**Not intended for direct use outside CI.** See [github-integration.md](../explanation/github-integration.md) for epic resolution details.

---

## `shipyard execute` (CI only)

Run the three-agent pipeline for unblocked issues.

**Purpose:** Runs the implementer → spec reviewer → code quality reviewer pipeline for each issue sequentially. Writes results to `shipyard-results.json` for the subsequent `publish-execution` step. Called by the `execute` job in `epic-driver.yml`.

**Flags:**

| Flag | Description |
|------|-------------|
| `-i`, `--input FILE` | Work JSON file (`SubtaskList`) from `shipyard find-work` (normal mode) |
| `--review-feedback-file FILE` | Review feedback file (revision mode) |
| `--prompt-file FILE` | Original task context file (revision mode) |

**Modes:**

- **Normal mode** (`-i`): reads the work payload and processes each unblocked task sequentially.
- **Revision mode** (`--review-feedback-file` + `--prompt-file`): addresses PR review feedback for a single previously-implemented task.

**Configuration:** The `CLAUDE_CODE_OAUTH_TOKEN` environment variable must be set for the Claude Code agents.

**Outputs:**

- Writes `shipyard-results.json` with `{ "successful": [<task ids>], "failed": [<task ids>] }`.
- Posts a comment on each failed issue explaining why it was skipped.
- Exits non-zero if any issues failed.

Does **not** create a branch, push, or open a PR — that is handled by `shipyard publish-execution`.

**Not intended for direct use outside CI.** See [agent-pipeline.md](../explanation/agent-pipeline.md) for pipeline details.

---

## `shipyard publish-execution` (CI only)

Push the implementation branch and open a pull request.

**Purpose:** Reads `shipyard-results.json` written by `shipyard execute`, pushes the branch, and opens a PR that closes all successfully-implemented issues. Skips silently if no issues succeeded. Called as the final step of the `execute` job in `epic-driver.yml`, with `if: always()` so it runs even if `shipyard execute` exits non-zero.

**Flags:**

| Flag | Description |
|------|-------------|
| `--branch TEXT` | Branch to push (required) |
| `-i`, `--input FILE` | Work JSON file (`SubtaskList`) produced by `shipyard find-work` (required) |
| `--results-file FILE` | Path to results JSON (default: value of `SHIPYARD_RESULTS_FILE`, fallback `shipyard-results.json`) |
| `--base-branch TEXT` | Base branch for the PR (default: value of `SHIPYARD_PR_BASE_BRANCH`, fallback `main`) |

**Outputs:**

- Pushes the branch to origin.
- Opens a PR titled `shipyard: implement N task(s) from epic #<N>` with `Closes #<n>` lines for each successful task.
- Prints the PR URL to stdout.

**Not intended for direct use outside CI.**

---

## `shipyard extract-github-event` (CI only)

Parse a GitHub Actions event and write structured outputs for use in subsequent workflow steps.

**Purpose:** Reads the event JSON at `$GITHUB_EVENT_PATH`, determines the trigger type (issue labeled `plan`, or pull request review with `CHANGES_REQUESTED`), fetches any needed issue/PR context via `gh`, and writes structured outputs to `$GITHUB_OUTPUT`. Also writes `prompt.txt` (and optionally `review-feedback.txt`) for `shipyard plan`. Called by the `plan` job in `plan-driver.yml`.

**Configuration:** Entirely via environment variables (set by the workflow):

| Variable | Description |
|----------|-------------|
| `GITHUB_EVENT_PATH` | Path to the event JSON (set automatically by Actions) |
| `GITHUB_REPOSITORY` | `owner/repo` (set automatically by Actions) |

**Outputs (to `$GITHUB_OUTPUT`):**

| Key | Populated when |
|-----|----------------|
| `issue_number` | Issue labeled `plan`, or re-plan of a plan PR |
| `issue_title` | Issue labeled `plan`, or re-plan of a plan PR |
| `has_review` | Always (`"true"` or `"false"`) |
| `pr_number` | Review event only |
| `branch_name` | Review event only |
| `review_target` | Review event only (`"plan"` or `"implementation"`) |

**Side effects:** Writes `prompt.txt` containing the issue/task context for `shipyard plan`. On review events, also writes `review-feedback.txt` combining the review summary and inline comments.

**Not intended for direct use outside CI.**

---

## `shipyard update-docs` (CI only)

Update documentation to reflect all changes made across an epic.

**Purpose:** Runs a documentation agent over the cumulative diff since `BASE_SHA`, commits the result, then iterates with a `doc_verifier` sub-agent until the verifier outputs LGTM. Called by the `update-docs` job in `epic-driver.yml` after an epic is fully implemented.

**Flags:**

| Flag | Description |
|------|-------------|
| `--base-sha TEXT` | Git SHA of the point where the epic branch diverged from main (required) |

**Configuration:** The `CLAUDE_CODE_OAUTH_TOKEN` environment variable must be set. Agent model and effort are controlled by the `SHIPYARD_DOC_MODEL`, `SHIPYARD_DOC_EFFORT`, `SHIPYARD_DOC_REVIEW_MODEL`, and `SHIPYARD_DOC_REVIEW_EFFORT` environment variables (see `shipyard/settings.py` for defaults).

**Outputs:**

- Commits documentation changes directly to the current branch.
- Does not push — the surrounding workflow step handles the push.

**Example:**

```bash
# Invoked by the workflow as:
shipyard update-docs --base-sha "$BASE_SHA"
```

**Not intended for direct use outside CI.** See [workflow.md](workflow.md) for how the surrounding workflow step computes `BASE_SHA`.
