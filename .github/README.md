# Workflow Testing

Shipyard's GitHub Actions workflows are tested locally using [act](https://github.com/nektos/act), which runs workflow jobs inside Docker containers. Tests use a custom image that pre-installs `gh` and intercepts mutating operations so no real GitHub API calls or git pushes are made during a test run.

## Prerequisites

- Docker (running)
- [act](https://github.com/nektos/act) installed as a `gh` extension:
  ```bash
  gh extension install nektos/gh-act
  ```

## One-time setup: build the test image

The custom image extends the standard act runner (`catthehacker/ubuntu:act-latest`) with:

- `gh` CLI pre-installed (so workflows don't need to install it at runtime)
- A `git` wrapper that swallows `git push` when `SHIPYARD_SIM_MODE=true`
- A `gh` wrapper that no-ops all GitHub API calls when `SHIPYARD_SIM_MODE=true`, returning plausible fake output for reads that the workflow consumes (e.g. `gh issue view`)

Build it once from the repo root:

```bash
docker build -t shipyard-act:latest .github/tests/
```

Rebuild whenever [`.github/tests/Dockerfile`](tests/Dockerfile) or the wrapper scripts under [`.github/tests/wrappers/`](tests/wrappers/) change.

## Sim mode

All test runs set `SHIPYARD_SIM_MODE=true` (via `.actrc`). In this mode:

| Operation | Behaviour |
|-----------|-----------|
| `git push` | Skipped — prints `[SIM] git push skipped` to stderr |
| `gh <any command>` | Skipped — prints `[SIM] gh …` to stderr; reads return stub data |
| Everything else | Runs normally inside the container |

Shipyard Python commands (`find-work`, `sync`, `execute`, …) also respect `SHIPYARD_SIM_MODE` internally and skip live API calls.

## Running the tests

### All workflows

```bash
bash .github/tests/test-all.sh
```

### Individual workflows

```bash
bash .github/tests/test-epic-driver.sh   # 3 scenarios
bash .github/tests/test-plan-driver.sh   # 2 scenarios
bash .github/tests/test-sync-driver.sh   # 1 scenario
```

### Dry run (validate workflow structure only, no containers)

```bash
bash .github/tests/test-all.sh --dry-run
```

### Single scenario

```bash
# Epic: issue labeled 'in-progress'
gh act issues \
  -e .github/tests/events/epic-issues-labeled.json \
  -W .github/workflows/epic-driver.yml

# Epic: merged implementation PR
gh act pull_request \
  -e .github/tests/events/epic-pr-merged.json \
  -W .github/workflows/epic-driver.yml

# Epic: manual dispatch
gh act workflow_dispatch \
  --input issue_number=42 \
  -W .github/workflows/epic-driver.yml

# Plan: issue labeled 'plan'
gh act issues \
  -e .github/tests/events/plan-issues-labeled.json \
  -W .github/workflows/plan-driver.yml

# Plan: review requesting changes
gh act pull_request_review \
  -e .github/tests/events/plan-review-changes-requested.json \
  -W .github/workflows/plan-driver.yml

# Sync: merged plan PR
gh act pull_request \
  -e .github/tests/events/sync-pr-merged-plan.json \
  -W .github/workflows/sync-driver.yml
```

## Configuration files

| File | Purpose |
|------|---------|
| `.actrc` | Global act flags: var file, `SHIPYARD_SIM_MODE=true`, custom image platform |
| `.github/tests/.actrc` | Test-specific flags: secrets file, container architecture |
| `.github/tests/vars` | GitHub Actions variables passed to every run |
| `.github/tests/.secrets` | Secrets file (not committed — create locally with fake tokens) |

### `.github/tests/.secrets` format

```
GITHUB_TOKEN=fake-token
CLAUDE_CODE_OAUTH_TOKEN=fake-token
```

The `gh` wrapper intercepts all API calls in sim mode, so the tokens don't need to be real.

## Event payloads

Synthetic event JSON files live in `.github/tests/events/`. Each file matches the shape of the real GitHub webhook payload for that trigger, with enough fields populated for the workflow conditions and step logic to work.

| File | Trigger |
|------|---------|
| `epic-issues-labeled.json` | Issue labeled `in-progress` |
| `epic-pr-merged.json` | Implementation PR merged |
| `epic-workflow-dispatch.json` | Manual dispatch with `issue_number` input |
| `plan-issues-labeled.json` | Issue labeled `plan` |
| `plan-review-changes-requested.json` | PR review requesting changes |
| `sync-pr-merged-plan.json` | Plan PR merged |
