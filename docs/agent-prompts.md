# Agent Prompts

Shipyard bundles four prompt files under `shipyard/prompts/`. Three are used at runtime by the CI pipeline; one is a helper for plan authoring.

## Prompt Files

| File | Role |
|------|------|
| `planner.md` | Instructions for writing a shipyard-compatible implementation plan |
| `implementer.md` | Drives the implementation agent |
| `spec-reviewer.md` | Drives the spec compliance review agent |
| `code-quality-reviewer.md` | Drives the code quality review agent |

## How Prompts Are Loaded

At runtime, `shipyard/commands/execute.py` resolves the prompts directory relative to the package:

```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```

Each prompt is read as plain text:

```python
implementer_tmpl = (PROMPTS_DIR / "implementer.md").read_text()
```

Then `format_prompt()` substitutes `{PLACEHOLDER}` tokens:

```python
def format_prompt(template: str, **kwargs: str) -> str:
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value)
    return template
```

## `planner.md`

**Used by:** Humans or planning agents, not by the CI pipeline.

**Purpose:** Instructs a Claude agent (or a human author) how to write a plan that will parse correctly and execute successfully. Covers:

- Required front matter (`# Title`, `**Goal:**`, `**Architecture:**`, `**Tech Stack:**`)
- Exact task block format (`### Task N:`, `**Depends on:**`, step-by-step with actual code)
- Rules: exact file paths, no placeholders, TDD steps with expected output
- Self-review checklist before saving

The planner prompt does not inject any placeholders — it is used as-is.

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
6. End the report with a status line: `DONE`, `DONE_WITH_CONCERNS`, `BLOCKED`, or `NEEDS_CONTEXT`.

The implementer runs in `bypassPermissions` mode with tools: `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`.

## `spec-reviewer.md`

**Used by:** `run_issue_pipeline()` after the implementer reports `DONE` or `DONE_WITH_CONCERNS`.

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

**Used by:** `run_issue_pipeline()` after the spec reviewer approves.

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

## Customizing Prompts for Maintainers

The prompts are plain text files included in the installed package via `package_data` (or equivalent). To customize them for a fork:

1. Edit the files in `shipyard/prompts/` directly.
2. Rebuild and reinstall the package.

Because `execute.py` resolves prompts relative to the installed package location, any changes will take effect on the next run without touching the workflow file.

If you want per-repository prompt customization (without forking shipyard), you could modify `PROMPTS_DIR` in `execute.py` to prefer a local `prompts/` directory when one exists — but this is not supported in the current release.
