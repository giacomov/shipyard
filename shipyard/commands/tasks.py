#!/usr/bin/env python3
"""shipyard tasks — extract tasks from a markdown plan using an AI agent."""

import asyncio
import os
from importlib.resources import files as _res_files
from pathlib import Path
from typing import Any

import click
import pydantic
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ProcessError,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from shipyard.settings import settings
from shipyard.utils.agent import report_results


class Subtask(pydantic.BaseModel):
    task_id: str
    title: str
    description: str
    blocked_by: set[str] = set()


class SubtaskList(pydantic.BaseModel):
    title: str
    description: str
    tasks: dict[str, Subtask] = {}

    def link_tasks(
        self,
        task_id: str,
        add_blocked_by: list[str] | None = None,
    ) -> dict:
        """Handle task dependencies created by the agent."""

        if task_id not in self.tasks:
            click.echo(f"Error: Task {task_id} not found for linking", err=True)

            return {"error": f"Task {task_id} not found for linking"}

        # Make sure all tasks exists
        add_blocked_by = add_blocked_by or []

        if not add_blocked_by:
            click.echo(f"Warning: No dependencies provided for task {task_id}", err=True)

            return {"error": f"You have to provide at least one dependency for task {task_id}."}

        for dep_id in add_blocked_by:
            if dep_id not in self.tasks:
                click.echo(f"Error: Dependency task {dep_id} not found for linking", err=True)

                return {
                    "error": f"Dependency task {dep_id} not found for linking. "
                    f"Make sure to first create all tasks, then link them in a second pass."
                }

        subtask = self.tasks[task_id]
        subtask.blocked_by.update(add_blocked_by)

        return {"success": True, "updated_task": subtask.model_dump()}


async def _run_task_agent(prompt: str, cwd: str, task_list: SubtaskList) -> None:
    # Define the custom tools
    @tool(
        "create_task",
        _res_files("shipyard.data.prompts").joinpath("create-task.md").read_text(),
        {"task_id": str, "title": str, "description": str},
    )
    async def create_task(args: dict[str, Any]) -> dict[str, Any]:
        task_id = args.get("task_id")
        title = args.get("title")
        description = args.get("description")

        if not task_id or not title or not description:
            click.echo("Error: Missing required fields for TaskCreate", err=True)

            return {
                "error": "Missing or empty required fields: task_id, title, and description are all required."
            }

        task = Subtask(task_id=task_id, title=title, description=description)
        task_list.tasks[task_id] = task

        return {"success": True, "created_task": task.model_dump()}

    @tool(
        "link_tasks",
        _res_files("shipyard.data.prompts").joinpath("link-tasks.md").read_text(),
        {
            "task_id": str,
            "add_blocked_by": list[str],
        },
    )
    async def link_tasks(args: dict[str, Any]) -> dict[str, Any]:
        return task_list.link_tasks(**args)

    # Wrap the tool in an in-process MCP server
    task_server = create_sdk_mcp_server(
        name="task_server",
        version="1.0.0",
        tools=[create_task, link_tasks],
    )

    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        mcp_servers={"task_server": task_server},
        allowed_tools=[
            "Read",
            "mcp__task_server__create_task",
            "mcp__task_server__link_tasks",
        ],
        cwd=cwd,
        effort="max",
    )

    async for message in query(prompt=prompt, options=options):
        report_results(message)
        match message:
            case AssistantMessage():
                for block in message.content:
                    match block:
                        case TextBlock():
                            click.echo(block.text, err=True)


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

    assert plan_path.exists(), f"Input file {plan_path} does not exist"

    task_list = SubtaskList(title=title, description=plan_path.read_text())

    TASK_AGENT_PROMPT = _res_files("shipyard.data.prompts").joinpath("task-agent.md").read_text()

    try:
        prompt = TASK_AGENT_PROMPT.format(plan_path=plan_path)
        asyncio.run(_run_task_agent(prompt, cwd=os.getcwd(), task_list=task_list))

    except ProcessError as e:
        raise click.ClickException(
            f"Claude CLI subprocess failed (exit code {e.exit_code}).\n"
            "The claude CLI's stderr output should appear above this message."
        ) from e

    except Exception as e:
        raise click.ClickException(f"Agent error: {e}") from e

    # Save the tasks to the outfile
    with open(output_file or settings.tasks_output_file, "w+") as f:
        f.write(task_list.model_dump_json(indent=4))

    click.echo(f"Saved {len(task_list.tasks)} tasks to {output_file or settings.tasks_output_file}")
