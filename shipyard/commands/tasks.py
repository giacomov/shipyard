#!/usr/bin/env python3
"""shipyard tasks — extract tasks from a markdown plan using an AI agent."""

import asyncio
import json
import os
from importlib.resources import files as _res_files
from pathlib import Path
from typing import Any

import click
import pydantic
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ProcessError,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
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
    committed: bool = False
    drafting: bool = True

    @pydantic.field_serializer("description")
    def truncate_description(self, v: str, info) -> str:
        if info.context and info.context.get("truncate"):
            return v[:50] + "..." if len(v) > 50 else v
        return v


async def receive_from_client(client: ClaudeSDKClient):
    async for message in client.receive_messages():
        match message:
            case AssistantMessage():
                for block in message.content:
                    match block:
                        case TextBlock():
                            click.echo(f"[text] {block.text}")
                        case ToolUseBlock():
                            click.echo(f"[tool] {block.name} {json.dumps(block.input)[:80]}...")
                        case ThinkingBlock():
                            click.echo(f"[thinking] {block.thinking}")

            case ResultMessage():
                report_results(message)

                break


async def _run_task_agent(prompt: str, cwd: str, task_list: SubtaskList) -> None:
    # Define the custom tools
    @tool(
        "create_task",
        _res_files("shipyard.data.prompts").joinpath("create-task.md").read_text(),
        {"task_id": str, "title": str, "description": str},
    )
    async def create_task(args: dict[str, Any]) -> dict[str, Any]:
        task_list.drafting = True

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
        "delete_task",
        _res_files("shipyard.data.prompts").joinpath("delete-task.md").read_text(),
        {"task_id": str},
    )
    async def delete_task(args: dict[str, Any]) -> dict[str, Any]:
        task_list.drafting = True

        task_id = args.get("task_id")

        if not task_id:
            click.echo("Error: Missing required field task_id for TaskDelete", err=True)

            return {"error": "Missing required field: task_id is required."}

        if task_id not in task_list.tasks:
            click.echo(f"Error: Task {task_id} not found for deletion", err=True)

            return {"error": f"Task {task_id} not found for deletion."}

        del task_list.tasks[task_id]

        # Also remove this task from any blocked_by lists
        for t in task_list.tasks.values():
            t.blocked_by.discard(task_id)

        return {"success": True, "deleted_task_id": task_id}

    @tool(
        "link_tasks",
        _res_files("shipyard.data.prompts").joinpath("link-tasks.md").read_text(),
        {
            "task_id": str,
            "add_blocked_by": list[str],
        },
    )
    async def link_tasks(args: dict[str, Any]) -> dict[str, Any]:
        task_list.drafting = True

        task_id = args.get("task_id")
        add_blocked_by = args.get("add_blocked_by")

        if task_id not in task_list.tasks:
            click.echo(f"Error: Task {task_id} not found for linking", err=True)

            return {"error": f"Task {task_id} not found for linking"}

        # Make sure all tasks exists
        add_blocked_by = add_blocked_by or []

        if not add_blocked_by:
            click.echo(f"Warning: No dependencies provided for task {task_id}", err=True)

            return {"error": f"You have to provide at least one dependency for task {task_id}."}

        for dep_id in add_blocked_by:
            if dep_id not in task_list.tasks:
                click.echo(f"Error: Dependency task {dep_id} not found for linking", err=True)

                return {
                    "error": f"Dependency task {dep_id} not found for linking. "
                    f"Make sure to first create all tasks, then link them in a second pass."
                }

        subtask = task_list.tasks[task_id]
        subtask.blocked_by.update(add_blocked_by)

        return {"success": True, "updated_task": subtask.model_dump()}

    @tool(
        "unlink_tasks",
        _res_files("shipyard.data.prompts").joinpath("unlink-tasks.md").read_text(),
        {
            "task_id": str,
            "remove_blocked_by": list[str],
        },
    )
    async def unlink_tasks(args: dict[str, Any]) -> dict[str, Any]:
        task_list.drafting = True

        task_id = args.get("task_id")
        remove_blocked_by = args.get("remove_blocked_by")

        if task_id not in task_list.tasks:
            click.echo(f"Error: Task {task_id} not found for unlinking", err=True)

            return {"error": f"Task {task_id} not found for unlinking"}

        # Make sure all tasks exists
        remove_blocked_by = remove_blocked_by or []

        if not remove_blocked_by:
            click.echo(
                f"Warning: No dependencies provided for unlinking from task {task_id}",
                err=True,
            )

            return {
                "error": f"You have to provide at least one dependency to unlink from task {task_id}."
            }

        for dep_id in remove_blocked_by:
            if dep_id not in task_list.tasks:
                click.echo(f"Error: Dependency task {dep_id} not found for unlinking", err=True)

                return {"error": f"Dependency task {dep_id} not found for unlinking. "}

        subtask = task_list.tasks[task_id]
        subtask.blocked_by.difference_update(remove_blocked_by)

        return {"success": True, "updated_task": subtask.model_dump()}

    @tool(
        "commit",
        "Commit the current list of tasks and their dependencies. ONLY CALL THIS AFTER REVIEWING",
        {},
    )
    async def commit(args: dict[str, Any]) -> dict[str, Any]:
        task_list.committed = True

        return {"success": True, "message": "Tasks committed."}

    # Wrap the tool in an in-process MCP server
    task_server = create_sdk_mcp_server(
        name="task_server",
        version="1.0.0",
        tools=[create_task, delete_task, link_tasks, unlink_tasks, commit],
    )

    options = ClaudeAgentOptions(
        permission_mode="dontAsk",
        mcp_servers={"task_server": task_server},
        allowed_tools=[
            "Read",
            "mcp__task_server__create_task",
            "mcp__task_server__delete_task",
            "mcp__task_server__link_tasks",
            "mcp__task_server__unlink_tasks",
            "mcp__task_server__commit",
        ],
        cwd=cwd,
        effort="max",
        system_prompt={"type": "preset", "preset": "claude_code"},
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        await receive_from_client(client)

        # We re-try up to 5 times
        for _ in range(5):
            # Here we should have a completed task list. Let's give it back to the model and ask for
            # review and confirmation
            graph = task_list.model_dump_json(indent=4, context={"truncate": True})

            task_list.drafting = False
            task_list.committed = False

            await client.query(
                f"""You defined the current tasks and their dependencies as follows:

                ```json
                {graph}
                ```

                Please review these tasks implement the original plan.

                If they are correct, please call the commit tool to confirm. Otherwise, fix them by calling the 
                available tools (like delete_task, unlink_tasks, create_task, link_tasks).
                """
            )

            await receive_from_client(client)

            if task_list.committed and not task_list.drafting:
                click.echo("Tasks committed by the agent.")
                break
            else:
                click.echo("Model has modified the task list, asking for review again...")
                continue

        else:
            click.echo(
                "Model did not commit the task list after 5 attempts. Task list might be incomplete."
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
