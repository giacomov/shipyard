# Workflows reference

Shipyard installs four GitHub Actions workflows via `shipyard init`.

---

## `epic-driver.yml`

Drives autonomous implementation. Triggered when a collaborator posts a `/ship run` comment on an epic issue, or when a Shipyard PR is merged.

### Triggers

```yaml
on:
  issue_comment:
    types: [created]       # /ship run comment on the epic issue
  pull_request:
    types: [closed]        # a Shipyard implementation PR was merged
```

The `find-work` job has an additional `if:` guard:

- `issue_comment` events: only when the comment starts with `/ship run` and the commenter is `OWNER`, `MEMBER`, or `COLLABORATOR`.
- `pull_request` events: only when the PR was merged (`merged == true`) and the PR's base branch starts with `shipyard/epic-`.

### How `shipyard init` works

`shipyard init [PATH]` copies all four templates from the installed package and substitutes `SHIPYARD_VERSION`:

```python
install_ref = "my-branch"  # if --dev my-branch, else the package version e.g. "0.1.0"
content = template.read_text().replace("SHIPYARD_VERSION", install_ref)
```

The result is a workflow that installs shipyard from a specific git ref:

```yaml
run: uv tool install "git+https://github.com/giacomov/shipyard@0.1.0"
```

Use `--dev BRANCH` to install from a branch instead of a pinned tag. Use `--force` to overwrite existing files. Use `--skip-plan-driver` to install only `epic-driver.yml` and `review-driver.yml` (skipping `plan-driver.yml` and `sync-driver.yml`).

`shipyard init` also installs agent skill files into `.claude/skills/shipyard-*/SKILL.md`. These skill files define the behavior of the implementer, reviewer, planner, and documentation agents. You can customize agent behavior by editing those files.

### Job structure

#### Job 1: `find-work`

```
runs-on: ubuntu-latest
permissions: contents: read, issues: write, pull-requests: read
```

Steps:

1. Set up uv.
2. Install shipyard.
3. **Close completed issues** (PR events only) — scans `PR_BODY` for `closes/fixes/resolves #N` patterns and closes each referenced issue.
4. **Find epic and unblocked issues** — runs `shipyard find-work` with event context in environment variables.

Flags passed to `shipyard find-work`:

| Flag | Source |
|------|--------|
| `--repo` | `github.repository` |
| `--issue-number` | `github.event.issue.number` — included only when non-empty (direct mode) |
| `--pr-body` | `github.event.pull_request.body` — passed via `$PR_BODY` env var to safely handle multiline text (PR mode) |

Outputs passed to the next jobs:

- `has_work` — `"true"` or `"false"`
- `work_json` — JSON string with epic and issue details (only when `has_work == "true"`)
- `epic_in_progress` — `"true"` or `"false"` — whether an active epic was found

#### Job 2: `execute`

```
runs-on: ubuntu-latest
needs: find-work
if: needs.find-work.outputs.has_work == 'true'
permissions: contents: write, pull-requests: write, issues: write, id-token: write
```

Steps:

1. `actions/checkout@v4` with `fetch-depth: 0` (full history needed for git operations).
2. Configure git identity (`github-actions[bot]`).
3. Set up uv.
4. Install shipyard.
5. **Write work JSON** — writes the `work_json` output from `find-work` into `/tmp/work.json`.
6. **Create implementation branch** — reads `/tmp/work.json` to get the epic number, fetches the existing `shipyard/epic-<N>` branch (created by `shipyard sync`), and creates a new `shipyard/epic-<N>-run-<RUN_ID>` branch from it. Sets `$SHIPYARD_BRANCH` (the run branch) and `$SHIPYARD_EPIC_BRANCH` (the epic base branch) in the environment.
7. **Run agent pipeline** — `shipyard execute -i /tmp/work.json` runs the three-agent pipeline for each unblocked issue and writes `shipyard-results.json`.
8. **Push branch and open PR** (`if: always()`) — `shipyard publish-execution --branch "$SHIPYARD_BRANCH" --base-branch "$SHIPYARD_EPIC_BRANCH" -i /tmp/work.json` pushes the branch and opens a PR against the epic branch if any issues succeeded. Runs even if `shipyard execute` exits non-zero, so partial results are always published.
9. **Post failure comment on epic issue** (`if: failure() && steps.run-pipeline.outcome == 'failure'`) — posts a comment on the epic issue with a link to the failed action run.

#### Job 3: `update-docs`

```
runs-on: ubuntu-latest
needs: find-work
if: needs.find-work.outputs.has_work == 'false' && github.event_name == 'pull_request' && github.event.pull_request.merged == true
permissions: contents: write, pull-requests: write, issues: read, id-token: write
```

Runs when a PR merges into a `shipyard/epic-*` branch and there is no remaining work (`has_work == 'false'`). This signals that the epic is complete.

Steps:

1. `actions/checkout@v4` with `fetch-depth: 0`.
2. Configure git identity (`github-actions[bot]`).
3. Set up uv and install shipyard.
4. **Check out epic branch and compute base SHA** — fetches and checks out the epic branch (`github.event.pull_request.base.ref`). Computes `BASE_SHA` as `git merge-base origin/<default_branch> HEAD`. This SHA covers the full cumulative diff of the epic.
5. **Run documentation agent** — `shipyard update-docs --base-sha "$BASE_SHA"` runs the doc agent over the cumulative diff, commits changes, then iterates with the `doc_verifier` sub-agent until it outputs LGTM.
6. **Commit and push documentation changes** — stages any uncommitted changes, commits, and pushes the epic branch.
7. **Open epic pull request** — opens a PR from the epic branch to the default branch titled `feat: epic #<N>: <EPIC_TITLE>` with body `All tasks for epic #<N> are complete. Closes #<N>.`

### How data flows between jobs

Both `execute` and `update-docs` consume the outputs written by `find-work`:

```yaml
# find-work job writes:
- name: Find epic and unblocked issues
  id: find-work
  run: shipyard find-work  # writes to $GITHUB_OUTPUT

# execute job reads:
WORK_JSON: ${{ needs.find-work.outputs.work_json }}
```

`shipyard find-work` writes outputs using the `key<<DELIMITER\nvalue\nDELIMITER` multiline format required for JSON values in `$GITHUB_OUTPUT`.

Within the `execute` job, `shipyard execute` writes `shipyard-results.json` which `shipyard publish-execution` reads in the next step.

### Required secrets

| Secret | Description |
|--------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for Claude Code agents. Add via: `gh secret set CLAUDE_CODE_OAUTH_TOKEN` |

`GH_TOKEN` is provided automatically by GitHub Actions and does not need to be set manually.

### Required Actions settings

In the repository's settings, enable **"Allow GitHub Actions to create and approve pull requests"** under **Settings → Actions → General → Workflow permissions**. Without this, the `publish-execution` and `update-docs` steps cannot open PRs.

---

## `plan-driver.yml`

Generates or updates implementation plans. Triggered when a `/ship plan` or `/ship replan` comment is posted on an issue or a plan PR.

### Triggers

```yaml
on:
  issue_comment:
    types: [created]       # /ship plan or /ship replan comment
```

The `plan` job guards on the comment starting with `/ship plan` or `/ship replan`, and the commenter being `OWNER`, `MEMBER`, or `COLLABORATOR`.

A concurrency group (`plan-driver-<issue-number>`) ensures only one planning run per issue runs at a time, cancelling any in-progress run.

### Job structure

#### Job: `plan`

```
runs-on: ubuntu-latest
permissions: contents: write, pull-requests: write, issues: write, id-token: write
```

Steps:

1. `actions/checkout@v4` with `fetch-depth: 0`.
2. Set up uv and install shipyard.
3. **Extract GitHub event context** — `shipyard extract-github-event` parses the trigger event and writes structured outputs (`issue_number`, `issue_title`, `has_review`, `pr_number`, etc.) and writes `prompt.txt` (and `review-feedback.txt` on re-plan).
4. Configure git identity.
5. **Checkout branch** — checks out or creates `shipyard-plan/i<N>`.
6. **Generate or update plan** — `shipyard plan` runs the planning agent and writes `plans/i<N>.md`. On re-plan (`/ship replan` on a plan PR), also passes `--pr-number`, `--review-feedback-file`, and `--existing-plan-path`.
7. **Commit and publish** — commits the plan file and either pushes a new branch and opens a PR (initial plan, titled `Plan: <ISSUE_TITLE>`) or pushes to the existing branch (re-plan). On initial plan, posts a comment on the issue with the PR URL.

### Plan vs. re-plan

| Mode | Trigger | Branch | Output |
|------|---------|--------|--------|
| Initial plan | `/ship plan` comment on issue | Created: `shipyard-plan/i<N>` | PR opened against main; issue commented with PR URL |
| Re-plan | `/ship replan` comment on plan PR | Existing `shipyard-plan/i<N>` | Branch pushed; existing PR updated |

---

## `sync-driver.yml`

Automatically converts a merged plan PR into GitHub Issues. Triggered when a PR from a `shipyard-plan/i<N>` or `plan/i<N>` branch is merged.

### Triggers

```yaml
on:
  pull_request:
    types: [closed]
```

The `sync` job guards on `merged == true` and the PR head branch starting with `shipyard-plan/` or `plan/`.

### Job structure

#### Job: `sync`

```
runs-on: ubuntu-latest
permissions: contents: write, issues: write, id-token: write
```

Steps:

1. `actions/checkout@v4` with `ref: github.event.pull_request.base.ref` — checks out the PR base branch so the merged plan file is available.
2. Set up uv and install shipyard.
3. **Extract issue number** — parses the branch name (`shipyard-plan/i<N>` or `plan/i<N>`) to get `N`.
4. **Generate `tasks.json`** — fetches the issue title via `gh issue view`, then runs `shipyard tasks -i plans/i<N>.md --title "Implementation: <ISSUE_TITLE>" -o tasks.json` to convert the plan into structured JSON.
5. **Sync to GitHub Issues** — `shipyard sync -i tasks.json --repo <repository>` creates the epic issue and sub-issues.

### Required secrets

| Secret | Description |
|--------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for the `shipyard tasks` planning agent |

`GH_TOKEN` is provided automatically.

---

## `review-driver.yml`

Addresses PR review feedback autonomously. Triggered when a reviewer requests changes on a Shipyard implementation PR (any PR whose head branch starts with `shipyard/`).

### Triggers

```yaml
on:
  pull_request_review:
    types: [submitted]
```

The `revise` job has an additional `if:` guard: the review state must be `CHANGES_REQUESTED` and the PR head branch must start with `shipyard/`.

### Job structure

#### Job: `revise`

```
runs-on: ubuntu-latest
permissions: contents: write, pull-requests: write, issues: read, id-token: write
```

Steps:

1. `actions/checkout@v4` — checks out the PR head branch with `fetch-depth: 0`.
2. Configure git identity (`github-actions[bot]`).
3. Set up uv and install shipyard.
4. **Extract review context** — `shipyard extract-github-event` reads the review event, fetches inline comments, and writes `review-feedback.txt` (combined review summary and inline comments) and `prompt.txt` (original task context from the PR's closing references).
5. **Run revision pipeline** (`id: revise`) — `shipyard execute --review-feedback-file review-feedback.txt --prompt-file prompt.txt` runs in revision mode: addresses the review feedback, re-runs the spec and code quality reviewers, and runs tests.
6. **Push revised branch** (`if: success()`) — pushes the updated head branch to origin.
7. **Post failure comment on PR** (`if: failure() && steps.revise.outcome == 'failure'`) — posts a comment on the PR with a link to the action run.

### Required secrets

| Secret | Description |
|--------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for Claude Code agents. Same secret as `epic-driver.yml`. |

`GH_TOKEN` is provided automatically by GitHub Actions.

---

## Dogfooding

The shipyard repository itself uses all four workflows to implement its own features. The workflows in `.github/workflows/` were generated by running `shipyard init` and point to the version of shipyard currently in use.

Plans are triggered with `/ship plan` comments on issues. Merged plans trigger `sync-driver.yml`. Implementation runs autonomously via `epic-driver.yml` when `/ship run` is commented or a Shipyard PR is merged.
