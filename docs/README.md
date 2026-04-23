# Shipyard documentation

Shipyard is an agentic GitHub Actions pipeline that autonomously implements GitHub Issues. You write a markdown plan, shipyard converts it into a structured task board on GitHub Issues, and a CI workflow picks up unblocked tasks one by one — spawning Claude Code agents that implement, commit, and open pull requests without human intervention.

## How-to guides

| Guide | Description |
|-------|-------------|
| [Run your first epic](how-to/run-your-first-epic.md) | Set up Shipyard and run the full pipeline end-to-end |

## Reference

| Doc | Contents |
|-----|----------|
| [CLI reference](reference/cli.md) | All eight CLI commands with flags and examples |
| [Task format](reference/task-format.md) | Markdown plan syntax, JSON schemas, round-trip example |
| [Workflows](reference/workflow.md) | `epic-driver.yml`, `plan-driver.yml`, `sync-driver.yml` jobs, secrets |
| [Agent prompts](reference/agent-prompts.md) | Bundled prompts and how to customize them |

## Explanation

| Doc | Contents |
|-----|----------|
| [Architecture](explanation/architecture.md) | Problem, component overview, codemap, invariants |
| [Agent pipeline](explanation/agent-pipeline.md) | Three-agent pipeline, retry logic, failure handling |
| [GitHub integration](explanation/github-integration.md) | Issues, sub-issues, blocked-by, epic resolution, permissions |
