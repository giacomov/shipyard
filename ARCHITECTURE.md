# Architecture

Shipyard solves the coordination problem in agentic coding: given a multi-task implementation plan, how do you sequence work, recover from failures, and accumulate results across many AI agent runs — without a dedicated server? The answer is to use GitHub Issues as the task graph, GitHub Actions as the scheduler, and the `gh` CLI as the only interface to GitHub's API. No database. No long-running process. No infrastructure beyond a standard GitHub repo.

## Bird's-eye view

**Plan authoring (local):** A developer writes a markdown plan → `shipyard tasks` runs an AI agent to extract tasks into a dependency graph (tasks.json) → `shipyard sync` materializes it as GitHub Issues with `blocked-by` edges and an epic branch.

**Work resolution (CI, find-work job):** GitHub event context → `shipyard find-work` resolves the active epic and filters sub-issues to those with no open blockers → writes a JSON payload to `$GITHUB_OUTPUT`.

**Implementation (CI, execute job):** Work JSON → `shipyard execute` runs a three-agent pipeline (implementer → spec reviewer → code quality reviewer) for each task sequentially → writes `shipyard-results.json` → `shipyard publish-execution` pushes the branch and opens a PR.

**Documentation (CI, update-docs job):** When the last PR in an epic is merged and there is no more work, `shipyard update-docs` runs a documentation agent over the cumulative epic diff, commits after the first pass, then iterates with a verifier sub-agent until it outputs LGTM. The surrounding workflow step pushes to the epic branch.

## Codemap

```
shipyard/
  cli.py               # Click entry point; wires all commands into the `shipyard` group
  settings.py          # Settings: SHIPYARD_* env var config with defaults
  sim.py               # Sim mode flag: is_sim_mode() reads SHIPYARD_SIM_MODE; used by agent.py and gh.py
  commands/
    init.py            # shipyard init — copies workflow templates, substitutes SHIPYARD_VERSION
    tasks.py           # shipyard tasks — runs an AI agent to extract tasks from a markdown plan; writes tasks.json
    sync.py            # shipyard sync — tasks.json → GitHub Issues + epic branch via gh CLI
    find_work.py       # shipyard find-work — epic resolution + unblocked sub-issue lookup; writes $GITHUB_OUTPUT
    execute.py         # shipyard execute — async three-agent pipeline; writes shipyard-results.json
    plan.py            # shipyard plan — planning agent runner; writes plans/i<N>.md
    publish.py         # shipyard publish-execution — git push + gh pr create; reads shipyard-results.json
    update_docs.py     # shipyard update-docs — doc agent + verifier loop; CI use only
  data/
    prompts/           # plain-text prompt files loaded via importlib.resources (currently: system-prompt.md)
    skills/            # agent skill SKILL.md files installed into the target repo by `shipyard init`
    templates/         # epic-driver.yml, review-driver.yml, plan-driver.yml, sync-driver.yml with SHIPYARD_VERSION placeholder
  schemas/
    subtask.py         # Subtask: task_id, title, description, blocked_by
    subtask_list.py    # SubtaskList: epic_id, title, description, tasks dict; shared by tasks.json and work JSON
  utils/
    git.py             # git subprocess wrappers: checkout, push, reset, get_head_sha
    gh.py              # gh CLI wrappers: gh, resolve_repo, create_pull_request, close_issues_body, GitHub output helpers
    github_event.py    # extract-github-event command + event parsing helpers
    agent.py           # SimSDKClient, get_sdk_client, and receive_from_client helpers
```

Key types: `SubtaskList` (the shared schema between `shipyard tasks` output and `shipyard execute` input), `ClaudeSDKClient` (wraps `claude-agent-sdk` query calls).

## Invariants

**GitHub Issues are the only persistent store.** There is no database, no queue, no cache. All state lives in GitHub Issues: epic status, task status, dependency edges, failure comments.

**All GitHub API calls go through the `gh` CLI as subprocesses.** No code in this repo makes direct HTTP calls to api.github.com. The `gh` subprocess boundary is deliberate: it means local auth, org SSO, and API preview flags are handled by `gh`, not by this codebase.

**CI-only commands are not intended for direct use.** `execute.py`, `plan.py`, `publish.py`, and `update_docs.py` carry no `--repo`, `--token`, or similar auth/targeting flags — GitHub auth is handled by the `gh` CLI and Claude auth by `CLAUDE_CODE_OAUTH_TOKEN`. (`find_work.py` does accept `--repo` as a required flag, since the workflow passes it explicitly.) All operational parameters are passed as CLI flags by the surrounding workflow steps. None of these commands are designed for interactive use outside CI.

**`shipyard execute` never pushes or opens a PR.** Branch push and PR creation are `shipyard publish-execution`'s responsibility. This separation allows `publish-execution` to run with `if: always()` in the workflow, ensuring partial results are always published even when the pipeline exits non-zero.

**The epic branch is created by `shipyard sync` (local phase), never by CI.** The CI `execute` job creates a run branch off the epic branch, but the epic branch itself (`shipyard/epic-<N>`) must exist before any CI run starts.

**Failure handling always resets to `base_sha`.** When a task fails, `execute.py` runs `git reset --hard base_sha` before moving to the next task, and the workflow posts a failure comment on the epic issue or PR. This ensures failed task attempts leave no commits on the branch.

**The `blocked-by` API soft-fails.** If the GitHub dependency API is unavailable (not supported on all plans), `sync.py` logs a warning and continues. Tasks are treated as unblocked in this case — the ordering guarantee depends on the API being available.

## Cross-cutting concerns

**Error handling:** In the pipeline, any exception during a task's agent run triggers `reset_fn(base_sha)` to reset git state. The workflow then posts a failure comment on the epic issue (normal mode) or the PR (revision mode) with a link to the action run. Execution continues to the next task. `shipyard execute` exits 1 if any task failed.

**Configuration:** Local commands (`init`, `tasks`, `sync`) use CLI flags. CI commands (`find-work`, `execute`, `plan`, `publish-execution`, `update-docs`) are invoked by the surrounding workflow steps with CLI flags for per-run parameters (e.g., `--repo`, `-i`, `--branch`, `--base-sha`) and read cross-cutting settings from environment variables (`GITHUB_REPOSITORY`, `CLAUDE_CODE_OAUTH_TOKEN`, `SHIPYARD_*` model/effort vars, etc.).

**Authentication:** The `gh` CLI handles all GitHub authentication (personal access token or OIDC). The `CLAUDE_CODE_OAUTH_TOKEN` environment variable authenticates calls to the Claude Code API and is unrelated to GitHub auth.

**Prompt loading:** The system prompt and task-extraction agent prompts are plain text files under `shipyard/data/prompts/`, loaded via `importlib.resources`. The implementer, spec reviewer, code quality reviewer, planner, replanner, doc agent, and doc verifier are driven by skill files under `shipyard/data/skills/`, which `shipyard init` installs into `.claude/skills/` in the target repository.

**Testability:** `reset_fn` in `execute.py` is an injectable callback (defaults to a no-op in tests), making the pipeline testable without live git state.
