#!/usr/bin/env python3
"""shipyard tasks — extract tasks from a markdown plan using an AI agent."""

import asyncio
import os
from importlib.resources import files as _res_files
from pathlib import Path
from typing import Any

import click
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ProcessError,
    create_sdk_mcp_server,
    tool,
)

from shipyard.schemas import Subtask, SubtaskList
from shipyard.settings import settings
from shipyard.sim import is_sim_mode
from shipyard.utils.agent import get_sdk_client, receive_from_client

_system_prompt = _res_files("shipyard.data.prompts").joinpath("system-prompt.md").read_text()

_TASKS_JSON_EXCLUDE: dict = {"committed": True, "drafting": True, "epic_id": True}


async def _tool_create_task(args: dict[str, Any], task_list: SubtaskList) -> dict[str, Any]:
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


async def _tool_delete_task(args: dict[str, Any], task_list: SubtaskList) -> dict[str, Any]:
    task_list.drafting = True

    task_id = args.get("task_id")

    if not task_id:
        click.echo("Error: Missing required field task_id for TaskDelete", err=True)
        return {"error": "Missing required field: task_id is required."}

    if task_id not in task_list.tasks:
        click.echo(f"Error: Task {task_id} not found for deletion", err=True)
        return {"error": f"Task {task_id} not found for deletion."}

    del task_list.tasks[task_id]

    for t in task_list.tasks.values():
        t.blocked_by.discard(task_id)

    return {"success": True, "deleted_task_id": task_id}


async def _tool_link_tasks(args: dict[str, Any], task_list: SubtaskList) -> dict[str, Any]:
    task_list.drafting = True

    task_id = args.get("task_id")
    add_blocked_by = args.get("add_blocked_by")

    if task_id not in task_list.tasks:
        click.echo(f"Error: Task {task_id} not found for linking", err=True)
        return {"error": f"Task {task_id} not found for linking"}

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


async def _tool_unlink_tasks(args: dict[str, Any], task_list: SubtaskList) -> dict[str, Any]:
    task_list.drafting = True

    task_id = args.get("task_id")
    remove_blocked_by = args.get("remove_blocked_by")

    if task_id not in task_list.tasks:
        click.echo(f"Error: Task {task_id} not found for unlinking", err=True)
        return {"error": f"Task {task_id} not found for unlinking"}

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


async def _tool_commit(args: dict[str, Any], task_list: SubtaskList) -> dict[str, Any]:
    task_list.committed = True
    return {"success": True, "message": "Tasks committed."}


async def _run_task_agent(prompt: str, cwd: str, task_list: SubtaskList) -> None:
    # Define the custom tools
    @tool(
        "create_task",
        _res_files("shipyard.data.skills.shipyard-task-agent")
        .joinpath("create-task.md")
        .read_text(),
        {"task_id": str, "title": str, "description": str},
    )
    async def create_task(args: dict[str, Any]) -> dict[str, Any]:
        return await _tool_create_task(args, task_list)

    @tool(
        "delete_task",
        _res_files("shipyard.data.skills.shipyard-task-agent")
        .joinpath("delete-task.md")
        .read_text(),
        {"task_id": str},
    )
    async def delete_task(args: dict[str, Any]) -> dict[str, Any]:
        return await _tool_delete_task(args, task_list)

    @tool(
        "link_tasks",
        _res_files("shipyard.data.skills.shipyard-task-agent")
        .joinpath("link-tasks.md")
        .read_text(),
        {
            "task_id": str,
            "add_blocked_by": list[str],
        },
    )
    async def link_tasks(args: dict[str, Any]) -> dict[str, Any]:
        return await _tool_link_tasks(args, task_list)

    @tool(
        "unlink_tasks",
        _res_files("shipyard.data.skills.shipyard-task-agent")
        .joinpath("unlink-tasks.md")
        .read_text(),
        {
            "task_id": str,
            "remove_blocked_by": list[str],
        },
    )
    async def unlink_tasks(args: dict[str, Any]) -> dict[str, Any]:
        return await _tool_unlink_tasks(args, task_list)

    @tool(
        "commit",
        "Commit the current list of tasks and their dependencies. ONLY CALL THIS AFTER REVIEWING",
        {},
    )
    async def commit(args: dict[str, Any]) -> dict[str, Any]:
        return await _tool_commit(args, task_list)

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
        system_prompt=_system_prompt,
        setting_sources=["project"],
        model=settings.planning_model,
        effort=settings.planning_effort,
    )

    async with get_sdk_client(options) as client:
        await client.query(prompt)

        await receive_from_client(client)

        # We re-try up to 5 times
        for _ in range(5):
            # Here we should have a completed task list. Let's give it back to the model and ask for
            # review and confirmation
            graph = task_list.model_dump_json(
                indent=4,
                exclude=_TASKS_JSON_EXCLUDE,
                context={"truncate": True},
            )

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
    help=f"Output JSON file (default: {settings.tasks_output_file})",
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

    try:
        prompt = (
            f"Use the shipyard-task-agent skill.\n\nThe implementation plan is at: {plan_path}\n"
        )
        asyncio.run(_run_task_agent(prompt, cwd=os.getcwd(), task_list=task_list))

        if is_sim_mode() and not task_list.tasks:
            task_list.tasks["T-001"] = Subtask(
                task_id="T-001",
                title="[Sim] Placeholder task",
                description="Simulated task produced in sim mode.",
            )
            task_list.committed = True

    except ProcessError as e:
        raise click.ClickException(
            f"Claude CLI subprocess failed (exit code {e.exit_code}).\n"
            "The claude CLI's stderr output should appear above this message."
        ) from e

    except Exception as e:
        raise click.ClickException(f"Agent error: {e}") from e

    # Save the tasks to the outfile
    with open(output_file or settings.tasks_output_file, "w+") as f:
        f.write(task_list.model_dump_json(indent=4, exclude=_TASKS_JSON_EXCLUDE))

    click.echo(f"Saved {len(task_list.tasks)} tasks to {output_file or settings.tasks_output_file}")
