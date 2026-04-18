# Architecture

## High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Developer machine                                              │
│                                                                 │
│  plan.md ──► shipyard tasks ──► tasks.json                      │
│                                      │                          │
│                                      ▼                          │
│                              shipyard sync                      │
└─────────────────────────────────────┬───────────────────────────┘
                                      │ gh CLI
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  GitHub                                                         │
│                                                                 │
│  Epic issue  ◄──── sub-issues (tasks) with blocked-by edges     │
│       │                                                         │
│  "in-progress" label added                                      │
│       │                                                         │
│       └──── triggers epic-driver.yml                            │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions (CI)                                            │
│                                                                 │
│  find-work job                                                  │
│    shipyard find-work ──► work_json output                      │
│                                      │                          │
│  execute job (if has_work == true)   │                          │
│    1. git checkout -b <branch>       │                          │
│    2. shipyard execute ◄─────────────┘                          │
│       │   Implementer agent                                     │
│       │   Spec Reviewer agent                                   │
│       │   Code Quality Reviewer agent                           │
│       └──► shipyard-results.json                                │
│    3. shipyard publish-execution                                 │
│           └──► git push + gh pr create                          │
└─────────────────────────────────────────────────────────────────┘
```

## Three Layers

### 1. Plan Authoring (local)

The developer writes a structured markdown plan and uses the `tasks` and `sync` CLI commands to materialize it as GitHub Issues. This is the only step that requires a human.

### 2. GitHub Issues as Task Board

GitHub Issues serve as the persistent task board. The epic issue is the root node; sub-issues are individual tasks. `blocked-by` dependency edges enforce ordering. Shipyard reads issue state (open/closed, blockers) at runtime to determine what to work on next. No external database is required.

### 3. CI Execution (GitHub Actions)

Every trigger event (label added, PR merged, manual dispatch) runs `find-work` to resolve the current epic and discover unblocked sub-issues, then passes a JSON payload to the `execute` job. That job runs in three steps: create the branch, run the agent pipeline (`shipyard execute`), and publish the results (`shipyard publish-execution`).

## Main Tools

| Tool | Role |
|------|------|
| [Click](https://click.palletsprojects.com/) | CLI framework for all commands |
| `claude-agent-sdk` | Async agent execution via `query()` |
| `gh` CLI | All GitHub API calls (issues, sub-issues, PRs, labels) |
| GitHub Actions | Workflow orchestration, event routing |

## Data Flow

```
markdown plan
    │
    │  shipyard tasks
    ▼
tasks.json  { title, description, tasks: {id: {task_id, title, description, status, blocked_by}} }
    │
    │  shipyard sync  (gh CLI)
    ▼
GitHub Issues  (epic + sub-issues + blocked-by edges + in-progress label)
    │
    │  epic-driver.yml  (triggered by label / PR merge / dispatch)
    ▼
work_json  SubtaskList { epic_id, title, description, tasks: {id → Subtask} }
    │
    │  shipyard execute  (claude-agent-sdk)
    ▼
shipyard-results.json  { successful: [...], failed: [...] }
    │
    │  shipyard publish-execution
    ▼
git branch + commits + PR
```

## Package Layout

```
shipyard/
  __init__.py          # empty, marks package; py.typed present
  cli.py               # Click group wiring all commands
  commands/
    __init__.py
    init.py            # shipyard init — copies workflow templates
    tasks.py           # shipyard tasks — markdown → JSON parser
    sync.py            # shipyard sync — JSON → GitHub Issues
    find_work.py       # shipyard find-work — epic resolution + unblocked lookup
    execute.py         # shipyard execute — three-agent pipeline runner (CI only)
    plan.py            # shipyard plan — planning agent runner (CI only)
    publish.py         # shipyard publish-execution — push branch + open PR (CI only)
  prompts/
    planner.md         # prompt for plan authoring (used by humans / plan agents)
    implementer.md     # prompt for the implementer agent
    spec-reviewer.md   # prompt for the spec compliance reviewer
    code-quality-reviewer.md  # prompt for the code quality reviewer
  templates/
    epic-driver.yml    # bundled workflow template (SHIPYARD_VERSION placeholder)
    plan-driver.yml    # bundled plan workflow template (SHIPYARD_VERSION placeholder)
  utils/
    git.py             # git subprocess wrappers (checkout, push, reset, get_head_sha, …)
    gh.py              # gh CLI wrappers + GitHub output helpers (post_issue_comment, create_pull_request, …)
    github_event.py    # extract-github-event command + event parsing helpers
```
