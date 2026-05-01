# Agent prompts reference

Shipyard bundles prompt files under `shipyard/data/prompts/`. These files are loaded at runtime by the CI pipeline via `importlib.resources`.

All agents — implementer, spec reviewer, code quality reviewer, planner, replanner, doc agent, doc verifier, and task-extraction agent — are driven by **skill files** installed into `.claude/skills/shipyard-*/SKILL.md` by `shipyard init`. Edit those files to customize agent behavior.

---

## Bundled prompt files

| File | Role |
|------|------|
| `system-prompt.md` | System prompt injected into every agent session |

## How prompts are loaded

At runtime, command modules read prompts using `importlib.resources`:

```python
from importlib.resources import files as _res_files

prompt = _res_files("shipyard.data.prompts").joinpath("system-prompt.md").read_text()
```

Because prompts are bundled with the installed package, no filesystem path configuration is needed.

## `system-prompt.md`

**Used by:** every agent session (`tasks`, `execute`, `plan`, `update-docs`).

Injected as the Claude `system` prompt. Sets global behavior constraints shared across all agent roles.

---

## Agent skill files

All agents are implemented as Claude Code skills, not bundled prompts. `shipyard init` installs them into `.claude/skills/` in the target repository.

| Skill file | Role |
|------------|------|
| `shipyard-implementer/SKILL.md` | Drives the implementation agent |
| `shipyard-spec-reviewer/SKILL.md` | Drives the spec compliance review agent |
| `shipyard-code-quality-reviewer/SKILL.md` | Drives the code quality review agent |
| `shipyard-planner/SKILL.md` | Drives the initial planning agent |
| `shipyard-replanner/SKILL.md` | Drives the re-planning agent |
| `shipyard-doc-agent/SKILL.md` | Drives the documentation update agent |
| `shipyard-doc-verifier/SKILL.md` | Drives the documentation review agent |
| `shipyard-task-agent/SKILL.md` | Drives the task-extraction agent (`shipyard tasks`) |

The `shipyard-task-agent` skill directory also contains the MCP tool description files (`create-task.md`, `delete-task.md`, `link-tasks.md`, `unlink-tasks.md`) used as `description` fields for the in-process MCP tools registered by `shipyard tasks`.

### How skill files are invoked

In `execute.py`, the implementer agent is started with:

```python
await client.query(f"Use the shipyard-implementer skill.\n\n{task_context}")
```

In `tasks.py`, the task-extraction agent is started with:

```python
await client.query(f"Use the shipyard-task-agent skill.\n\nThe implementation plan is at: {plan_path}\n")
```

After the agent populates the task list, `shipyard tasks` runs a review loop — serializing the current task graph and asking the agent to confirm or correct it — before writing `tasks.json`.

Sub-agents are registered via `AgentDefinition` and invoked by the implementer through the `Agent` tool:

```python
"spec_reviewer": AgentDefinition(
    prompt="Use the shipyard-spec-reviewer skill.",
    tools=["Bash", "Read", "Grep", "Glob"],
    ...
)
```

### Customizing skill files

Edit `.claude/skills/shipyard-*/SKILL.md` in your repository to customize agent behavior. Changes take effect on the next pipeline run without any rebuild or reinstall. Skill files are not bundled into the installed package — they live in your repository.

To reset a skill file to the default bundled version, run:

```bash
shipyard init --force
```
