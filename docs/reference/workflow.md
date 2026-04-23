# Workflows reference

Shipyard installs three GitHub Actions workflows via `shipyard init`.

---

## `epic-driver.yml`

Drives autonomous implementation. Triggered when an epic issue is labeled `in-progress`, when a PR merges, or via manual dispatch.

### Triggers

```yaml
on:
  issues:
    types: [labeled]          # epic labeled "in-progress"
  pull_request:
    types: [closed]           # a PR was merged (may close a sub-issue)
  workflow_dispatch:
    inputs:
      issue_number:
        description: "Epic issue number to drive"
        required: true
```

The `find-work` job has an additional `if:` guard to ignore irrelevant events:

- `issues` events: only when the label added is `in-progress` and it's not a PR.
- `pull_request` events: only when the PR was actually merged (`merged == true`).
- `workflow_dispatch`: always.

### How `shipyard init` works

`shipyard init [PATH]` copies all three templates from the installed package and substitutes `SHIPYARD_VERSION`:

```python
install_ref = "main"  # if --from-main, else the package version e.g. "0.1.0"
content = template.read_text().replace("SHIPYARD_VERSION", install_ref)
```

The result is a workflow that installs shipyard from a specific git ref:

```yaml
run: uv tool install "git+https://github.com/giacomov/shipyard@0.1.0"
```

Use `--from-main` to install from the HEAD of `main` instead of a pinned tag. Use `--force` to overwrite existing files. Use `--skip-plan-driver` to only install `epic-driver.yml`.

### Job structure

#### Job 1: `find-work`

```
runs-on: ubuntu-latest
permissions: contents: read, issues: read, pull-requests: read
```

Steps:
1. Set up uv.
2. `uv tool install git+https://github.com/giacomov/shipyard@<ref>` — no checkout needed.
3. Run `shipyard find-work` with event context in environment variables.

Outputs passed to the next job:
- `has_work` — `"true"` or `"false"`
- `work_json` — JSON string with epic and issue details

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
4. `uv tool install git+https://github.com/giacomov/shipyard@<ref>`.
5. **Write work JSON** — writes the `work_json` output from `find-work` into `work.json`.
6. **Create implementation branch** — reads `work.json` to get the epic number, fetches the existing `shipyard/epic-<N>` branch (created by `shipyard sync`), and creates a new `shipyard/epic-<N>-run-<RUN_ID>` branch from it. Sets `$SHIPYARD_BRANCH` (the run branch) and `$SHIPYARD_EPIC_BRANCH` (the epic base branch) in the environment.
7. **Run agent pipeline** — `shipyard execute -i work.json` runs the three-agent pipeline for each unblocked issue and writes `shipyard-results.json`.
8. **Push branch and open PR** (`if: always()`) — `shipyard publish-execution --branch "$SHIPYARD_BRANCH" --base-branch "$SHIPYARD_EPIC_BRANCH" -i work.json` pushes the branch and opens a PR against the epic branch if any issues succeeded. Runs even if `shipyard execute` exits non-zero, so partial results are always published.

#### Job 3: `update-docs`

```
runs-on: ubuntu-latest
needs: find-work
if: needs.find-work.outputs.has_work == 'false' && github.event_name == 'pull_request' && github.event.pull_request.merged == true
permissions: contents: write, id-token: write
```

Runs when a PR merges and there is no remaining work (`has_work == 'false'`). This signals that the epic is complete.

Steps:
1. `actions/checkout@v4` with `fetch-depth: 0`.
2. Configure git identity (`github-actions[bot]`).
3. Set up uv and install shipyard.
4. **Check out epic branch and compute base SHA** — derives the epic branch name from `github.event.pull_request.head.ref`, fetches and checks it out, then computes `BASE_SHA` as `git merge-base origin/<base.ref> HEAD` (where `<base.ref>` is `github.event.pull_request.base.ref`). This SHA covers the full cumulative diff of the epic.
5. **Run documentation agent** — `shipyard update-docs --base-sha "$BASE_SHA"` runs the doc agent over the cumulative diff, commits changes, then iterates with the `doc_verifier` sub-agent until it outputs LGTM.
6. **Push documentation changes** — pushes the updated epic branch to origin.

### How data flows between jobs

The two jobs communicate via GitHub Actions step outputs:

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

---

## `plan-driver.yml`

Generates or updates implementation plans. Triggered when an issue is labeled `plan`, or when a pull request review is submitted with `CHANGES_REQUESTED`.

### Triggers

```yaml
on:
  issues:
    types: [labeled]          # issue labeled "plan"
  pull_request_review:
    types: [submitted]        # reviewer requests changes on a plan PR
```

The `plan` job guards on `github.event.label.name == 'plan'` (for issues) or `github.event.review.state == 'CHANGES_REQUESTED'` (for reviews).

### Job structure

#### Job: `plan`

```
runs-on: ubuntu-latest
permissions: contents: write, pull-requests: write, issues: write, id-token: write
```

Steps:
1. `actions/checkout@v4` with `fetch-depth: 0`.
2. Set up uv and install shipyard.
3. **Extract GitHub event context** — `shipyard extract-github-event` parses the trigger event and writes structured outputs (`issue_number`, `issue_title`, `has_review`, `pr_number`, etc.).
4. Configure git identity (`github-actions[bot]`).
5. **Checkout plan branch** — creates `plan/i<N>` for new plans, or fetches and checks out the existing branch for re-plans.
6. **Generate or update plan** — `shipyard plan` runs the planning agent and writes `plans/i<N>.md`. On re-plan, also passes `--existing-plan-path` and `--review-feedback-file`.
7. **Commit and publish plan** — commits the plan file and either pushes a new branch + opens a draft PR (initial plan) or force-pushes to the existing branch (re-plan).

### Plan vs. re-plan

| Mode | Trigger | Branch | PR |
|------|---------|--------|----|
| Initial plan | Issue labeled `plan` | Created: `plan/i<N>` | Draft PR opened |
| Re-plan | Review `CHANGES_REQUESTED` on plan PR | Existing `plan/i<N>` checked out | Existing PR updated |

---

## `sync-driver.yml`

Automatically converts a merged plan PR into GitHub Issues. Triggered when a PR labeled `plan` is merged.

### Triggers

```yaml
on:
  pull_request:
    types: [closed]
```

The `sync` job guards on `merged == true` and the PR having the `plan` label.

### Job structure

#### Job: `sync`

```
runs-on: ubuntu-latest
permissions: contents: read, issues: write, id-token: write
```

Steps:
1. `actions/checkout@v4` — checks out the base branch (main) so the merged plan file is available.
2. Set up uv and install shipyard.
3. **Extract issue number** — parses the branch name (`plan/i<N>`) to get `N`.
4. **Generate `tasks.json`** — `shipyard tasks -i plans/i<N>.md --title "Implementation: <ISSUE_TITLE>" -o tasks.json` runs the task-parsing agent to convert the plan into structured JSON.
5. **Sync to GitHub Issues** — `shipyard sync -i tasks.json --no-in-progress-label` creates the epic issue and sub-issues. The `--no-in-progress-label` flag skips the label so the epic automation does not start automatically; the developer adds it manually when ready.

### Required secrets

| Secret | Description |
|--------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for the `shipyard tasks` planning agent |

`GH_TOKEN` is provided automatically.

---

## Dogfooding

The shipyard repository itself uses all three workflows to implement its own features. The workflows in `.github/workflows/` were generated by running `shipyard init` and point to the version of shipyard currently in use. Plans are written and labeled `plan` to trigger `plan-driver.yml`, merged to trigger `sync-driver.yml`, and implemented autonomously via `epic-driver.yml`.

See the most recent commits for examples of shipyard-generated PRs.
