# CLI reference

Shipyard exposes nine commands through the `shipyard` entry point.

```
shipyard --help
```

---

## `shipyard init`

Set up the Shipyard workflows in a repository.

**Purpose:** Copies the bundled `epic-driver.yml`, `review-driver.yml`, `plan-driver.yml`, and `sync-driver.yml` templates into `.github/workflows/` and substitutes `SHIPYARD_VERSION` with the installed package version (or the given branch when `--dev BRANCH` is set).

**Arguments and flags:**

| Name | Type | Description |
|------|------|-------------|
| `PATH` | positional argument | Target repository directory (default: `.`) |
| `--force` | flag | Overwrite existing workflow files and skill files |
| `--skip-plan-driver` | flag | Only install `epic-driver.yml` and `review-driver.yml`, skip `plan-driver.yml` and `sync-driver.yml` |
| `--dev BRANCH` | option | Install shipyard from this branch instead of the pinned version |

**Outputs:**

- `.github/workflows/epic-driver.yml` and `review-driver.yml` — always installed.
- `.github/workflows/plan-driver.yml` and `sync-driver.yml` — skipped when `--skip-plan-driver` is set.
- `.claude/skills/shipyard-*/SKILL.md` — agent skill files for the implementer, spec reviewer, code quality reviewer, planner, replanner, doc agent, doc verifier, and task-extraction agent. Edit these files to customize agent behavior.

**Example:**

```bash
# Scaffold both workflows in the current repo
shipyard init

# Scaffold into a different repo directory
shipyard init ../my-other-repo

# Overwrite existing workflows
shipyard init --force

# Install from main branch (useful before tagging a release)
shipyard init --dev main

# Install from a feature branch
shipyard init --dev my-feature-branch

# Only install the epic driver
shipyard init --skip-plan-driver
```

After running:

1. Commit the generated files: `git add .github .claude && git commit -m 'chore: add shipyard workflows and agent skills'`
2. Add `CLAUDE_CODE_OAUTH_TOKEN` as a repository secret.
3. Enable **"Allow GitHub Actions to create and approve pull requests"** under **Settings → Actions → General → Workflow permissions**.

---

## `shipyard tasks`

Extract tasks from a markdown plan using an AI agent.

**Purpose:** Runs a `ClaudeSDKClient` AI agent that reads the markdown plan and calls structured tools (`create_task`, `delete_task`, `link_tasks`, etc.) to populate a `SubtaskList`. Writes the result to `tasks.json` (or to `--output` if specified), suitable for `shipyard sync`.

**Flags:**

| Flag | Description |
|------|-------------|
| `-i`, `--input FILE` | Input markdown file (required) |
| `-t`, `--title TEXT` | Epic issue title written into `tasks.json` (required) |
| `-o`, `--output FILE` | Output JSON file (default: `tasks.json`) |

**Inputs:** A markdown plan file. See [task-format.md](task-format.md) for the expected structure.

**Outputs:** A JSON object with `title`, `description`, and `tasks` (a dict keyed by task ID). See [task-format.md](task-format.md) for the schema.

**Example:**

```bash
# Extract to default tasks.json
shipyard tasks -i plan.md -t "My Feature Plan"

# Extract to a named file
shipyard tasks -i plan.md -t "My Feature Plan" -o tasks.json
```

Exits non-zero if the agent subprocess fails.

---

## `shipyard sync`

Sync task JSON to GitHub Issues.

**Purpose:** Creates the epic issue, one sub-issue per task, links them via the GitHub sub-issues API, and wires `blocked-by` dependency edges.

**Flags:**

| Flag | Description |
|------|-------------|
| `-i`, `--input FILE` | Input `tasks.json` (default: stdin) |
| `--repo OWNER/REPO` | Target repository (default: auto-detected via `gh repo view`) |

**Inputs:** The JSON produced by `shipyard tasks`.

**Outputs:** Prints progress to stdout. On success, prints URLs for the epic and each task issue, and creates and pushes the `shipyard/epic-<N>` branch that the CI workflow will use as the base for implementation PRs.

**Example:**

```bash
# Sync to current repo
shipyard sync -i tasks.json

# Sync to a specific repo
shipyard sync -i tasks.json --repo myorg/myrepo
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

**Purpose:** Resolves the active epic (directly from `--issue-number`, or by parsing closing references in `--pr-body`), queries GitHub for open sub-issues with no open blockers, and writes a JSON payload to `$GITHUB_OUTPUT`. Called by the `find-work` job in `epic-driver.yml`.

**Flags:**

| Flag | Description |
|------|-------------|
| `--repo OWNER/REPO` | GitHub repository (required) |
| `--issue-number N` | Epic issue number — direct mode; when provided, `--pr-body` is ignored |
| `--pr-body TEXT` | PR body text — PR mode; the epic is resolved by parsing closing references |

One of `--issue-number` or `--pr-body` must be provided.

**Outputs (to `$GITHUB_OUTPUT`):**

| Key | Value |
|-----|-------|
| `has_work` | `"true"` or `"false"` |
| `work_json` | JSON payload for `shipyard execute` (only when `has_work=true`) |
| `epic_in_progress` | `"true"` or `"false"` — whether an active epic was found |

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

- **Normal mode only:** writes `shipyard-results.json` with `{ "successful": [<task ids>], "failed": [<task ids>] }`. Revision mode does not write a results file.
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

**Purpose:** Reads the event JSON at `$GITHUB_EVENT_PATH`, determines the trigger type (issue comment with `/ship plan`/`/ship replan`, or pull request review with `CHANGES_REQUESTED`), fetches any needed issue/PR context via `gh`, and writes structured outputs to `$GITHUB_OUTPUT`. Also writes `prompt.txt` (and optionally `review-feedback.txt`) for `shipyard plan` and `shipyard execute` (revision mode). Called by the `plan` job in `plan-driver.yml` and by the `revise` job in `review-driver.yml`.

**Configuration:** Entirely via environment variables (set by the workflow):

| Variable | Description |
|----------|-------------|
| `GITHUB_EVENT_PATH` | Path to the event JSON (set automatically by Actions) |
| `GITHUB_REPOSITORY` | `owner/repo` (set automatically by Actions) |
| `COMMENT_BODY` | Raw comment body (set by the workflow); used to detect `/ship replan` |

**Outputs (to `$GITHUB_OUTPUT`):**

| Key | Populated when |
|-----|----------------|
| `issue_number` | `/ship plan` comment on issue, or re-plan of a plan PR |
| `issue_title` | `/ship plan` comment on issue, or re-plan of a plan PR |
| `has_review` | Always (`"true"` or `"false"`) |
| `pr_number` | Review event, or `/ship replan` comment on a plan PR |

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
