#!/usr/bin/env python3
"""shipyard tasks — extract tasks from a markdown plan using an AI agent."""

import asyncio
import json
import os
import uuid
from pathlib import Path

import click
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ProcessError, TextBlock, query

from shipyard.utils.agent import report_results

_TASK_AGENT_PROMPT = """\
Read the implementation plan at {plan_path} and create tasks with dependencies for it \
using the TaskCreate tool.

Each task will be implemented and merged as a separate PR. Group work so each PR is
focused and cohesive — keep the total number of tasks small.

For each task call TaskCreate with:
- subject: short task title
- description: what must be implemented (be specific)
- blockedBy: list of task ids that must complete first (empty if none)

IMPORTANT: create tasks with dependencies.
"""


async def _run_task_agent(prompt: str, cwd: str) -> None:
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "TaskCreate"],
        cwd=cwd,
    )
    async for message in query(prompt=prompt, options=options):
        report_results(message)
        match message:
            case AssistantMessage():
                for block in message.content:
                    match block:
                        case TextBlock():
                            click.echo(block.text, err=True)


def _load_task_files(task_list_id: str) -> list[dict]:
    task_dir = Path.home() / ".claude" / "tasks" / task_list_id
    if not task_dir.exists():
        return []
    tasks = []
    for f in task_dir.iterdir():
        if f.suffix != ".json" or f.name.startswith("."):
            continue
        try:
            tasks.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    tasks.sort(key=lambda t: t.get("id", ""))
    return tasks


def validate(data: dict) -> None:
    """Raise ValueError if any dependency id is not a known task id."""
    known_ids = {t["id"] for t in data["tasks"]}
    for task in data["tasks"]:
        for dep in task.get("dependencies", []):
            if dep not in known_ids:
                raise ValueError(
                    f"Task {task['id']} has unknown dependency '{dep}'. "
                    f"Known task ids: {sorted(known_ids)}"
                )


@click.command()
@click.option(
    "-i",
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Input markdown plan file",
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(),
    default=None,
    help="Output JSON file (default: stdout)",
)
@click.option(
    "-t",
    "--title",
    required=True,
    help="Epic issue title written into tasks.json",
)
def tasks(input_file: str, output_file: str | None, title: str) -> None:
    """Extract tasks from a markdown plan using an AI agent."""
    plan_path = Path(input_file).resolve()
    task_list_id = str(uuid.uuid4())

    env_backup = os.environ.get("CLAUDE_CODE_TASK_LIST_ID")
    os.environ["CLAUDE_CODE_TASK_LIST_ID"] = task_list_id
    try:
        prompt = _TASK_AGENT_PROMPT.format(plan_path=plan_path)
        asyncio.run(_run_task_agent(prompt, cwd=os.getcwd()))
    except ProcessError as e:
        raise click.ClickException(
            f"Claude CLI subprocess failed (exit code {e.exit_code}).\n"
            "The claude CLI's stderr output should appear above this message."
        ) from e
    except Exception as e:
        raise click.ClickException(f"Agent error: {e}") from e
    finally:
        if env_backup is None:
            os.environ.pop("CLAUDE_CODE_TASK_LIST_ID", None)
        else:
            os.environ["CLAUDE_CODE_TASK_LIST_ID"] = env_backup

    raw_tasks = _load_task_files(task_list_id)
    if not raw_tasks:
        raise click.ClickException("Agent created no tasks")

    result: dict = {
        "title": title,
        "body": "",
        "tasks": [
            {
                "id": t["id"],
                "subject": t["subject"],
                "description": t.get("description", ""),
                "status": "pending",
                "dependencies": t.get("blockedBy", []),
            }
            for t in raw_tasks
        ],
    }

    try:
        validate(result)
    except ValueError as e:
        raise click.ClickException(str(e))

    output = json.dumps(result, indent=2)
    if output_file:
        Path(output_file).write_text(output)
    else:
        click.echo(output)
