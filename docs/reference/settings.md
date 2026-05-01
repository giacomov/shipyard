# Settings reference

Shipyard reads configuration from `SHIPYARD_*` environment variables. All settings have defaults defined in `shipyard/settings.py`.

Set these variables in your CI environment (repository secrets or workflow `env:` blocks) to override defaults.

---

## Agent model and effort

These variables control which Claude model and effort level each agent uses.

| Variable | Default | Description |
|----------|---------|-------------|
| `SHIPYARD_PLANNING_MODEL` | See `settings.py` | Model for the `shipyard tasks` task-extraction agent and the `shipyard plan` planning agent |
| `SHIPYARD_PLANNING_EFFORT` | See `settings.py` | Effort level for the task-extraction and planning agents (`low`, `medium`, or `high`) |
| `SHIPYARD_EXECUTION_MODEL` | See `settings.py` | Model for the `shipyard execute` implementer agent |
| `SHIPYARD_EXECUTION_EFFORT` | See `settings.py` | Effort level for the implementer agent |
| `SHIPYARD_REVIEW_MODEL` | See `settings.py` | Model for the spec reviewer and code quality reviewer sub-agents |
| `SHIPYARD_REVIEW_EFFORT` | See `settings.py` | Effort level for the reviewer sub-agents |
| `SHIPYARD_REVISION_MODEL` | See `settings.py` | Model for the revision-mode implementer (`--review-feedback-file`) |
| `SHIPYARD_REVISION_EFFORT` | See `settings.py` | Effort level for the revision-mode implementer |
| `SHIPYARD_DOC_MODEL` | See `settings.py` | Model for the `shipyard update-docs` documentation agent |
| `SHIPYARD_DOC_EFFORT` | See `settings.py` | Effort level for the documentation agent |
| `SHIPYARD_DOC_REVIEW_MODEL` | See `settings.py` | Model for the `doc_verifier` sub-agent |
| `SHIPYARD_DOC_REVIEW_EFFORT` | See `settings.py` | Effort level for the `doc_verifier` sub-agent |

Model values are short names recognized by the Claude SDK (e.g., `"sonnet"`, `"opus"`). Effort values are `"low"`, `"medium"`, or `"high"`.

## Retry limits

| Variable | Default | Description |
|----------|---------|-------------|
| `SHIPYARD_PLANNER_MAX_RETRIES` | See `settings.py` | Maximum number of retry attempts when the planning agent fails to write the plan file |

## File paths

| Variable | Default | Description |
|----------|---------|-------------|
| `SHIPYARD_TASKS_OUTPUT_FILE` | `tasks.json` | Default output path for `shipyard tasks` |
| `SHIPYARD_RESULTS_FILE` | `shipyard-results.json` | Path where `shipyard execute` writes results; read by `shipyard publish-execution` |
| `SHIPYARD_PLANS_DIR` | `plans` | Directory where `shipyard plan` writes plan files (`plans/i<N>.md`) |

## PR base branch

| Variable | Default | Description |
|----------|---------|-------------|
| `SHIPYARD_PR_BASE_BRANCH` | `main` | Default base branch for PRs opened by `shipyard publish-execution` when `--base-branch` is not set |

---

For exact default values, read `shipyard/settings.py` directly. Documenting them here would cause drift as they change.
