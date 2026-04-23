# Architecture

Shipyard solves the coordination problem in agentic coding: given a multi-task implementation plan, how do you sequence work, recover from failures, and accumulate results across many AI agent runs — without a dedicated server? The answer is to use GitHub Issues as the task graph, GitHub Actions as the scheduler, and the `gh` CLI as the only interface to GitHub's API. No database. No long-running process. No infrastructure beyond a standard GitHub repo.

## Bird's-eye view

**Plan authoring (local):** A developer writes a markdown plan → `shipyard tasks` parses it into a dependency graph (tasks.json) → `shipyard sync` materializes it as GitHub Issues with `blocked-by` edges and an epic branch.

**Work resolution (CI, find-work job):** GitHub event context → `shipyard find-work` resolves the active epic and filters sub-issues to those with no open blockers → writes a JSON payload to `$GITHUB_OUTPUT`.

**Implementation (CI, execute job):** Work JSON → `shipyard execute` runs a three-agent pipeline (implementer → spec reviewer → code quality reviewer) for each task sequentially → writes `shipyard-results.json` → `shipyard publish-execution` pushes the branch and opens a PR.

## Codemap

```
shipyard/
  cli.py               # Click entry point; wires all commands into the `shipyard` group
  settings.py          # ShipyardSettings: pr_base_branch and other defaults
  commands/
    init.py            # shipyard init — copies workflow templates, substitutes SHIPYARD_VERSION
    tasks.py           # shipyard tasks — markdown → ParsedPlan → tasks.json; pure, no I/O side effects
    sync.py            # shipyard sync — tasks.json → GitHub Issues + epic branch via gh CLI
    find_work.py       # shipyard find-work — epic resolution + unblocked sub-issue lookup; writes $GITHUB_OUTPUT
    execute.py         # shipyard execute — async three-agent pipeline; writes shipyard-results.json
    plan.py            # shipyard plan — planning agent runner; writes plans/i<N>.md
    publish.py         # shipyard publish-execution — git push + gh pr create; reads shipyard-results.json
  data/
    prompts/           # plain-text prompt templates with {PLACEHOLDER} tokens; loaded via importlib.resources
    templates/         # epic-driver.yml, plan-driver.yml, sync-driver.yml with SHIPYARD_VERSION placeholder
  schemas/
    subtask.py         # Subtask: task_id, title, description, status, blocked_by
    subtask_list.py    # SubtaskList: epic_id, title, description, tasks dict; shared by tasks.json and work JSON
  utils/
    git.py             # git subprocess wrappers: checkout, push, reset, get_head_sha
    gh.py              # gh CLI wrappers: post_issue_comment, create_pull_request, GitHub output helpers
    github_event.py    # extract-github-event command + event parsing helpers
    agent.py           # ClaudeSDKClient wrapper and AgentDefinition helpers
```

Key types: `SubtaskList` (the shared schema between `shipyard tasks` output and `shipyard execute` input), `ParsedPlan` (intermediate from the markdown parser), `ClaudeSDKClient` (wraps `claude-agent-sdk` query calls).

## Invariants

**GitHub Issues are the only persistent store.** There is no database, no queue, no cache. All state lives in GitHub Issues: epic status, task status, dependency edges, failure comments.

**All GitHub API calls go through the `gh` CLI as subprocesses.** No code in this repo makes direct HTTP calls to api.github.com. The `gh` subprocess boundary is deliberate: it means local auth, org SSO, and API preview flags are handled by `gh`, not by this codebase.

**CI-only commands take no interactive options.** `find_work.py`, `execute.py`, `plan.py`, and `publish.py` read all configuration from environment variables. They have no `--repo`, `--token`, or similar flags. This is what makes them safe to run in an unattended CI job.

**`shipyard execute` never pushes or opens a PR.** Branch push and PR creation are `shipyard publish-execution`'s responsibility. This separation allows `publish-execution` to run with `if: always()` in the workflow, ensuring partial results are always published even when the pipeline exits non-zero.

**The epic branch is created by `shipyard sync` (local phase), never by CI.** The CI `execute` job creates a run branch off the epic branch, but the epic branch itself (`shipyard/epic-<N>`) must exist before any CI run starts.

**Failure handling always resets to `base_sha`.** When a task fails, `execute.py` runs `git reset --hard base_sha` before moving to the next task. This ensures failed task attempts leave no commits on the branch.

**The `blocked-by` API soft-fails.** If the GitHub dependency API is unavailable (not supported on all plans), `sync.py` logs a warning and continues. Tasks are treated as unblocked in this case — the ordering guarantee depends on the API being available.

## Cross-cutting concerns

**Error handling:** In the pipeline, any exception during a task's agent run triggers `reset_fn(base_sha)` (default: `git reset --hard`) and `comment_fn(issue_id, reason)` (default: posts a GitHub Issue comment with an HTML tag `<!-- shipyard-executor: REASON -->`). Execution continues to the next task. `shipyard execute` exits 1 if any task failed.

**Configuration:** Local commands (`init`, `tasks`, `sync`) use CLI flags. CI commands (`find-work`, `execute`, `plan`, `publish-execution`) use environment variables exclusively — `GITHUB_REPOSITORY`, `EVENT_NAME`, `ISSUE_NUMBER`, `CLAUDE_CODE_OAUTH_TOKEN`, etc.

**Authentication:** The `gh` CLI handles all GitHub authentication (personal access token or OIDC). The `CLAUDE_CODE_OAUTH_TOKEN` environment variable authenticates calls to the Claude Code API and is unrelated to GitHub auth.

**Prompt loading:** All agent prompts are plain text files under `shipyard/data/prompts/`. They are loaded at runtime via `importlib.resources`, so they are bundled with the installed package and require no filesystem path configuration.

**Testability:** `reset_fn` and `comment_fn` in `execute.py` are injectable callbacks (default to no-ops in tests), making the pipeline testable without live git or GitHub state.
