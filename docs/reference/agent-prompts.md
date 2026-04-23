# Agent prompts reference

Shipyard bundles prompt files under `shipyard/data/prompts/`. They are used at runtime by the CI pipeline.

## Prompt files

| File | Role |
|------|------|
| `system-prompt.md` | System prompt injected into every agent session |
| `implementer.md` | Drives the implementation agent |
| `spec-reviewer.md` | Drives the spec compliance review agent |
| `code-quality-reviewer.md` | Drives the code quality review agent |
| `task-agent.md` | Drives the task management agent |
| `create-task.md` | Sub-prompt for creating a task |
| `delete-task.md` | Sub-prompt for deleting a task |
| `link-tasks.md` | Sub-prompt for linking tasks |
| `unlink-tasks.md` | Sub-prompt for unlinking tasks |

## How prompts are loaded

At runtime, `shipyard/commands/execute.py` reads prompts using `importlib.resources`:

```python
from importlib.resources import files as _res_files

prompt = _res_files("shipyard.data.prompts").joinpath("implementer.md").read_text()
```

Placeholder substitution uses Python's built-in `.format()`:

```python
prompt.format(TASK_DESCRIPTION=task_description, CONTEXT=context)
```

## `implementer.md`

**Used by:** `run_issue_pipeline()` in `execute.py` for each issue.

**Injected placeholders:**

| Placeholder | Value |
|-------------|-------|
| `{TASK_DESCRIPTION}` | The GitHub Issue body (full text) |
| `{CONTEXT}` | `"Repository: {repo}\nEpic: #{n} — {title}\n{epic_body}"` plus, on retries, `"\n\n## Reviewer Feedback (attempt N)\n\n{feedback}"` |

**What it instructs the agent to do:**

1. Implement exactly what the task specifies.
2. Write tests using TDD (failing test first, then implementation).
3. Verify all tests pass.
4. Commit with descriptive messages.
5. Self-review for completeness, quality, discipline, and test coverage.

The implementer runs in `dontAsk` permission mode with tools: `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Agent`, `Monitor`.

After the implementer finishes, the pipeline instructs it (via a follow-up `query()`) to invoke the spec reviewer and code quality reviewer as sub-agents, fixing any issues they raise before moving on.

## `spec-reviewer.md`

**Used by:** `run_issue_pipeline()` as a registered sub-agent, invoked by the implementer after it commits.

**Injected placeholders:**

| Placeholder | Value |
|-------------|-------|
| `{TASK_DESCRIPTION}` | The GitHub Issue body |
| `{CONTEXT}` | Epic title + list of all tasks in the plan |
| `{BASE_SHA}` | The git SHA recorded before the implementer ran |

**What it instructs the agent to do:**

- Run `git diff {BASE_SHA}..HEAD` to identify what changed.
- Focus only on the changes — do not review pre-existing code.
- Check for missing requirements, extra unasked-for work, and misunderstandings.
- Report findings for the implementer to address.

Tools: `Bash`, `Read`, `Grep`, `Glob`.

## `code-quality-reviewer.md`

**Used by:** `run_issue_pipeline()` as a registered sub-agent, invoked by the implementer after the spec review passes.

**Injected placeholders:**

| Placeholder | Value |
|-------------|-------|
| `{TASK_DESCRIPTION}` | The GitHub Issue body |
| `{CONTEXT}` | Epic title + list of all tasks in the plan |
| `{BASE_SHA}` | The git SHA recorded before the implementer ran |

**What it instructs the agent to do:**

- Run `git diff --stat {BASE_SHA}..HEAD` and `git diff {BASE_SHA}..HEAD`.
- Focus only on the changes — do not review pre-existing code.
- Review: code quality, file structure, testing, architecture, and security.
- Report findings for the implementer to address.

Tools: `Bash`, `Read`, `Grep`, `Glob`.

## Customizing prompts

The prompts are plain text files included in the installed package under `shipyard/data/prompts/`. To customize them for a fork:

1. Edit the files in `shipyard/data/prompts/` directly.
2. Rebuild and reinstall the package.

Because `execute.py` reads prompts via `importlib.resources`, any changes take effect on the next run without touching the workflow file.
