# Workflows

Shipyard installs two GitHub Actions workflows via `shipyard init`.

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

### How `shipyard init` Works

`shipyard init [PATH]` copies both templates from the installed package and substitutes `SHIPYARD_VERSION`:

```python
install_ref = "main"  # if --from-main, else the package version e.g. "0.1.0"
content = template.read_text().replace("SHIPYARD_VERSION", install_ref)
```

The result is a workflow that installs shipyard from a specific git ref:

```yaml
run: uv tool install "git+https://github.com/giacomov/shipyard@0.1.0"
```

Use `--from-main` to install from the HEAD of `main` instead of a pinned tag. Use `--force` to overwrite existing files. Use `--skip-plan-driver` to only install `epic-driver.yml`.

### Job Structure

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
5. **Create implementation branch** — reads `$WORK_JSON` to get the epic number, creates `shipyard/epic-<N>-run-<RUN_ID>`, and sets `$SHIPYARD_BRANCH` in the environment.
6. **Run agent pipeline** — `shipyard execute` runs the three-agent pipeline for each unblocked issue and writes `shipyard-results.json`.
7. **Push branch and open PR** (`if: always()`) — `shipyard publish-execution --branch "$SHIPYARD_BRANCH"` pushes the branch and opens a PR if any issues succeeded. Runs even if `shipyard execute` exits non-zero, so partial results are always published.

### How Data Flows Between Jobs

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

### Required Secrets

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

### Job Structure

#### Job: `plan`

```
runs-on: ubuntu-latest
permissions: contents: write, pull-requests: write, issues: read, id-token: write
```

Steps:
1. `actions/checkout@v4` with `fetch-depth: 0`.
2. Set up uv and install shipyard.
3. **Extract GitHub event context** — `shipyard extract-github-event` parses the trigger event and writes structured outputs (`issue_number`, `issue_title`, `has_review`, `pr_number`, etc.).
4. Configure git identity (`github-actions[bot]`).
5. **Checkout plan branch** — creates `plan/i<N>` for new plans, or fetches and checks out the existing branch for re-plans.
6. **Generate or update plan** — `shipyard plan` runs the planning agent and writes `plans/i<N>.md`. On re-plan, also passes `--existing-plan-path` and `--review-feedback-file`.
7. **Commit and publish plan** — commits the plan file and either pushes a new branch + opens a draft PR (initial plan) or force-pushes to the existing branch (re-plan).

### Plan vs. Re-plan

| Mode | Trigger | Branch | PR |
|------|---------|--------|----|
| Initial plan | Issue labeled `plan` | Created: `plan/i<N>` | Draft PR opened |
| Re-plan | Review `CHANGES_REQUESTED` on plan PR | Existing `plan/i<N>` checked out | Existing PR updated |

---

## Dogfooding

The shipyard repository itself uses both workflows to implement its own features. The workflows in `.github/workflows/` were generated by running `shipyard init` and point to the version of shipyard currently in use. Plans are written using `planner.md`, converted to issues via `shipyard tasks` + `shipyard sync`, and implemented autonomously via `epic-driver.yml`.

See the most recent commits for examples of shipyard-generated PRs.
