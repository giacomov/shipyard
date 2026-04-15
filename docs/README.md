# Shipyard

Shipyard is an agentic GitHub Actions pipeline that autonomously implements GitHub Issues. You write a markdown plan, shipyard converts it into a structured task board on GitHub Issues, and a CI workflow picks up unblocked tasks one by one — spawning Claude Code agents that implement, commit, and open pull requests without human intervention.

## User Journey

1. **Write a plan** — author a markdown file describing your feature (or use `shipyard init` to scaffold the workflow, then let `planner.md` help you write a plan).
2. **Parse to JSON** — run `shipyard tasks -i plan.md -o tasks.json` to validate and convert the plan.
3. **Sync to GitHub** — run `shipyard sync -i tasks.json` to create the epic issue, sub-issues, and dependency (blocked-by) edges.
4. **Label the epic** — add the `in-progress` label to the epic issue to kick off the workflow.
5. **Watch PRs land** — the `epic-driver.yml` workflow finds unblocked sub-issues and runs a three-agent pipeline (implementer → spec reviewer → code quality reviewer) for each one, pushing a PR when all reviews pass.

## Prerequisites

- Python 3.12+
- [`gh` CLI](https://cli.github.com/) authenticated to your GitHub account
- `CLAUDE_CODE_OAUTH_TOKEN` secret added to your repository (for the CI workflow)

## Quick Start

```bash
# Install
pip install shipyard

# Scaffold the workflow into your repo
shipyard init

# Add the secret via GitHub CLI
gh secret set CLAUDE_CODE_OAUTH_TOKEN --body "<your-token>"

# Write a plan, then:
shipyard tasks -i my-plan.md -o tasks.json
shipyard sync -i tasks.json
# Then label the epic issue "in-progress" in the GitHub UI or via:
gh issue edit <epic-number> --add-label in-progress
```

## Wiki

| File | Contents |
|------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Component diagram, data flow, package layout |
| [cli.md](cli.md) | All five CLI commands with flags and examples |
| [agent-pipeline.md](agent-pipeline.md) | Three-agent pipeline, retry logic, failure handling |
| [task-format.md](task-format.md) | Markdown plan syntax, JSON schemas, round-trip example |
| [github-integration.md](github-integration.md) | Issues, sub-issues, blocked-by, labels, permissions |
| [workflow.md](workflow.md) | `epic-driver.yml` jobs, secrets, dogfooding |
| [agent-prompts.md](agent-prompts.md) | Four bundled prompts and how to customize them |
