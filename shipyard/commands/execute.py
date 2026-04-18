#!/usr/bin/env python3
"""shipyard execute — run the three-agent pipeline for unblocked issues (CI use only)."""

import asyncio
import json
from collections.abc import Callable
from importlib.resources import files as _res_files
from pathlib import Path

import click
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ClaudeSDKClient

from shipyard.schemas import Subtask, SubtaskList
from shipyard.settings import settings
from shipyard.utils.agent import receive_from_client
from shipyard.utils.gh import post_issue_comment, resolve_repo
from shipyard.utils.git import get_head_sha, reset_hard


async def run_issue_pipeline(
    task: Subtask,
    work: SubtaskList,
    base_sha: str,
    max_retries: int = 1,
    *,
    reset_fn: Callable[[str], None] = lambda _: None,
    comment_fn: Callable[[str, int, str], None] = lambda *_: None,
) -> bool:
    """Run implementer + spec reviewer + quality reviewer for one task.

    Returns True if all reviews pass and the task's commits should be kept.
    Returns False if the task failed; in that case the git state is reset to base_sha.
    """

    tasks_context = [
        f"- **Task {t.task_id}: {t.title}** [current task]"
        if t.task_id == task.task_id
        else f"- Task {t.task_id}: {t.title}"
        for t in work.tasks.values()
    ]

    task_description = f"Task {task.task_id}: {task.title}\n\n{task.description}"
    context = f"Epic: {work.title}\n\n{tasks_context}"

    implementer_prompt = (
        _res_files("shipyard.data.prompts")
        .joinpath("implementer.md")
        .read_text()
        .format(
            TASK_DESCRIPTION=task_description,
            CONTEXT=context,
        )
    )

    spec_reviewer_prompt = (
        _res_files("shipyard.data.prompts")
        .joinpath("spec-reviewer.md")
        .read_text()
        .format(
            TASK_DESCRIPTION=task_description,
            CONTEXT=context,
        )
    )

    code_quality_prompt = (
        _res_files("shipyard.data.prompts")
        .joinpath("code-quality-reviewer.md")
        .read_text()
        .format(
            TASK_DESCRIPTION=task_description,
            CONTEXT=context,
        )
    )

    options = ClaudeAgentOptions(
        permission_mode="dontAsk",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Monitor", "Grep", "Glob", "Agent"],
        system_prompt={"type": "preset", "preset": "claude_code"},
        setting_sources=["project"],
        model=settings.execution_model,
        effort=settings.execution_effort,
        agents={
            "spec_reviewer": AgentDefinition(
                description="Expert spec reviewer specialist. Verifies against the spec and provide feedback.",
                prompt=spec_reviewer_prompt,
                tools=["Read", "Grep", "Glob"],
                model=settings.review_model,
                effort=settings.review_effort,
            ),
            "code_quality_reviewer": AgentDefinition(
                description="Expert code quality reviewer specialist. Reviews the code for quality and provide feedback.",
                prompt=code_quality_prompt,
                tools=["Read", "Grep", "Glob"],
                model=settings.review_model,
                effort=settings.review_effort,
            ),
        },
    )

    async with ClaudeSDKClient(options=options) as client:
        # Implement
        await client.query(implementer_prompt)

        await receive_from_client(client)

        await client.query(
            "Now stage and commit your changes, without pushing yet. Make sure to include everything you changed."
        )

        await receive_from_client(client)

        # Review spec
        await client.query(
            """
            Now run the spec reviewer agent to review the implementation. If the implementation does not meet the spec, 
            fix the issues and re-run the spec reviewer until the implementation meets the spec.
            """
        )

        await receive_from_client(client)

        # Review code quality
        await client.query(
            """
            Now run the code quality reviewer agent to review the implementation. If the implementation does not meet the 
            code quality bar, fix the issues and re-run the code quality reviewer until the implementation meets the code 
            quality bar.
            """
        )

        await receive_from_client(client)

        # Run the tests
        await client.query(
            """
            If you changed any testable code, make sure there are tests for it, and run the tests until they pass.
            """
        )

        await receive_from_client(client)


async def run_all_issues(
    work: SubtaskList,
    *,
    reset_fn: Callable[[str], None] = lambda _: None,
    comment_fn: Callable[[str, int, str], None] = lambda *_: None,
) -> dict[str, bool]:
    """Run all tasks sequentially. Returns {task_id: success}."""
    results: dict[str, bool] = {}
    for task in work.tasks.values():
        print(f"\n── Implementing task {task.task_id}: {task.title}")
        base_sha = get_head_sha()
        success = await run_issue_pipeline(
            task,
            work,
            base_sha,
            settings.implementer_max_retries,
            reset_fn=reset_fn,
            comment_fn=comment_fn,
        )
        results[task.task_id] = success
        if success:
            print(f"   ✓ Task {task.task_id} implemented and approved")
        else:
            print(f"   ✗ Task {task.task_id} failed — commits reset")
    return results


@click.command()
@click.option(
    "-i",
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Work JSON file (SubtaskList) produced by shipyard find-work",
)
def execute(input_file: str) -> None:
    """Run the three-agent pipeline for unblocked tasks."""
    work = SubtaskList.model_validate_json(Path(input_file).read_text())
    repo = resolve_repo()

    results = asyncio.run(
        run_all_issues(
            work,
            reset_fn=reset_hard,
            comment_fn=lambda _, n, body: post_issue_comment(repo, n, body),
        )
    )

    successful = [tid for tid, ok in results.items() if ok]
    failed = [tid for tid, ok in results.items() if not ok]

    print(f"\n── Results: {len(successful)} succeeded, {len(failed)} failed")

    Path(settings.results_file).write_text(
        json.dumps(
            {
                "successful": successful,
                "failed": failed,
            }
        )
    )

    if failed:
        print(f"WARNING: {len(failed)} task(s) failed: {failed}")
        raise SystemExit(1)
