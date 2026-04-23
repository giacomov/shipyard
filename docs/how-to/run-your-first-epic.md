# Run your first epic

This guide walks you through setting up Shipyard in a repository and running the full pipeline from a markdown plan to merged pull requests.

## Prerequisites

- Python 3.13+
- [`gh` CLI](https://cli.github.com/) authenticated to your GitHub account
- A `CLAUDE_CODE_OAUTH_TOKEN` — an OAuth token for Claude Code agents

## 1. Install Shipyard

```bash
pip install shipyard
```

## 2. Scaffold the CI workflows

Run this from the root of the repository where you want the pipeline to run:

```bash
shipyard init
```

This creates three workflow files under `.github/workflows/`:
- `epic-driver.yml` — runs the agent pipeline when you label an epic `in-progress`
- `plan-driver.yml` — generates implementation plans from issues
- `sync-driver.yml` — converts merged plan PRs into GitHub Issues

Commit and push these files.

## 3. Add the OAuth secret

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN --body "<your-token>"
```

## 4. Write a plan

Create a markdown file following the [task format](../reference/task-format.md). A minimal example:

```markdown
# Add rate limiting Implementation Plan

**Goal:** Add per-user rate limiting to the API.

**Architecture:** Middleware layer checks a Redis counter before passing the request through.

**Tech Stack:** Python, Redis

---

### Task 1: Write the rate limiter middleware

**Depends on:** (none)

Implement `RateLimiterMiddleware` in `src/middleware.py`. ...

### Task 2: Wire the middleware into the app

**Depends on:** Task 1

Add `RateLimiterMiddleware` to the ASGI app stack in `src/app.py`. ...
```

## 5. Parse and sync the plan

```bash
# Convert the plan to structured JSON
shipyard tasks -i plan.md -t "Add rate limiting" -o tasks.json

# Create GitHub Issues from the JSON
shipyard sync -i tasks.json
```

`shipyard sync` prints the URLs of the epic issue and each sub-issue, and creates the `shipyard/epic-<N>` branch.

## 6. Start the pipeline

Label the epic issue `in-progress` to trigger `epic-driver.yml`:

```bash
gh issue edit <epic-number> --add-label in-progress
```

The workflow picks up unblocked sub-issues, runs the three-agent pipeline for each one, and opens a pull request against the epic branch.

## 7. Review and merge

Each pipeline run opens a PR titled `shipyard: implement N task(s) from epic #<N>`. Review the diff, request changes if needed, and merge when satisfied.

Merging the PR closes the implemented sub-issues and triggers another `epic-driver.yml` run, which picks up the next unblocked tasks.

## Stopping the pipeline

Remove the `in-progress` label from the epic issue, or close it. The workflow will not trigger again until the label is re-applied or a manual dispatch is run.
