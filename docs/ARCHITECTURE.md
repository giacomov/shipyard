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
│    shipyard execute ◄────────────────┘                          │
│       │                                                         │
│       ├── Implementer agent                                     │
│       ├── Spec Reviewer agent                                   │
│       └── Code Quality Reviewer agent                           │
│                │                                                │
│                └──► git push + gh pr create                     │
└─────────────────────────────────────────────────────────────────┘
```

## Three Layers

### 1. Plan Authoring (local)

The developer writes a structured markdown plan and uses the `tasks` and `sync` CLI commands to materialize it as GitHub Issues. This is the only step that requires a human.

### 2. GitHub Issues as Task Board

GitHub Issues serve as the persistent task board. The epic issue is the root node; sub-issues are individual tasks. `blocked-by` dependency edges enforce ordering. Shipyard reads issue state (open/closed, blockers) at runtime to determine what to work on next. No external database is required.

### 3. CI Execution (GitHub Actions)

Every trigger event (label added, PR merged, manual dispatch) runs `find-work` to resolve the current epic and discover unblocked sub-issues, then passes a JSON payload to `execute` which runs the agent pipeline for each issue.

## Main Tools

| Tool | Role |
|------|------|
| [Click](https://click.palletsprojects.com/) | CLI framework for all five commands |
| `claude-agent-sdk` | Async agent execution via `query()` |
| `gh` CLI | All GitHub API calls (issues, sub-issues, PRs, labels) |
| GitHub Actions | Workflow orchestration, event routing |

## Data Flow

```
markdown plan
    │
    │  shipyard tasks
    ▼
tasks.json  { title, body, tasks[{id, subject, description, status, dependencies}] }
    │
    │  shipyard sync  (gh CLI)
    ▼
GitHub Issues  (epic + sub-issues + blocked-by edges + in-progress label)
    │
    │  epic-driver.yml  (triggered by label / PR merge / dispatch)
    ▼
work_json  { epic_number, epic_title, epic_body, repo, issues[{number, title, body}] }
    │
    │  shipyard execute  (claude-agent-sdk)
    ▼
agent pipeline  ──►  git branch + commits + PR
```

## Package Layout

```
shipyard/
  __init__.py          # empty, marks package; py.typed present
  cli.py               # Click group wiring all commands
  commands/
    __init__.py
    init.py            # shipyard init — copies epic-driver.yml template
    tasks.py           # shipyard tasks — markdown → JSON parser
    sync.py            # shipyard sync — JSON → GitHub Issues
    find_work.py       # shipyard find-work — epic resolution + unblocked lookup
    execute.py         # shipyard execute — three-agent pipeline runner
  prompts/
    planner.md         # prompt for plan authoring (used by humans / plan agents)
    implementer.md     # prompt for the implementer agent
    spec-reviewer.md   # prompt for the spec compliance reviewer
    code-quality-reviewer.md  # prompt for the code quality reviewer
  templates/
    epic-driver.yml    # bundled workflow template (SHIPYARD_VERSION placeholder)
```
