#!/usr/bin/env python3
"""shipyard plan — generate or update an implementation plan for a GitHub issue."""

import asyncio
import os

import click
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from shipyard.settings import settings
from shipyard.utils.agent import receive_from_client

_RETRY_PROMPT = "You forgot to write the plan to {plan_path}. Please write it now."


def _plan_file_changed(plan_path: str, original_content: str | None) -> bool:
    """Return True if plan_path exists and its content differs from original_content."""
    if not os.path.exists(plan_path):
        return False
    with open(plan_path) as f:
        current = f.read()
    return current != (original_content or "")


async def run_plan_agent(
    prompt: str,
    cwd: str,
    plan_path: str,
    original_content: str | None,
) -> None:
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep", "Write"],
        cwd=cwd,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        await receive_from_client(client)

        for _ in range(settings.planner_max_retries):
            if _plan_file_changed(plan_path, original_content):
                return

            click.echo(f"Plan file not written to {plan_path}, retrying...", err=True)
            await client.query(_RETRY_PROMPT.format(plan_path=plan_path))
            await receive_from_client(client)

        if not _plan_file_changed(plan_path, original_content):
            raise RuntimeError(
                f"Planning agent failed to write plan file after "
                f"{settings.planner_max_retries} retries: {plan_path}"
            )


def _ensure_header(plan_path: str, issue_number: str) -> None:
    """Prepend the HTML comment header if the agent omitted it."""
    with open(plan_path) as f:
        content = f.read()
    header = f"<!-- Related to: #{issue_number} -->"
    if not content.startswith(header):
        with open(plan_path, "w") as f:
            f.write(header + "\n\n" + content)


@click.command()
@click.option("--prompt", "prompt_text", default=None, help="Inline planning context")
@click.option(
    "--prompt-file",
    default=None,
    type=click.Path(exists=True),
    help="File with planning context",
)
@click.option("--issue-number", default="local-test", help="Issue number")
@click.option("--issue-title", default=None, help="Issue title")
@click.option("--pr-number", default=None, type=int, help="PR number (re-planning run)")
@click.option(
    "--existing-plan-path",
    default=None,
    type=click.Path(),
    help="Previous plan file for context",
)
@click.option(
    "--review-feedback-file",
    default=None,
    type=click.Path(exists=True),
    help="Review feedback file",
)
def plan(
    prompt_text: str | None,
    prompt_file: str | None,
    issue_number: str,
    issue_title: str | None,
    pr_number: int | None,
    existing_plan_path: str | None,
    review_feedback_file: str | None,
) -> None:
    """Generate or update an implementation plan for a GitHub issue."""
    if prompt_text:
        context = prompt_text
    elif prompt_file is not None:
        with open(prompt_file) as f:
            context = f.read()
    else:
        raise click.UsageError("Provide --prompt or --prompt-file")

    cwd = os.getcwd()
    os.makedirs(settings.plans_dir, exist_ok=True)
    plan_path = f"{settings.plans_dir}/i{issue_number}.md"

    if pr_number is None:
        agent_prompt = (
            f"Use the shipyard-planner skill.\n\n"
            f"## Issue context\n\n{context}\n\n"
            f"Write the plan to: {plan_path}\n"
            f"Start the file with `<!-- Related to: #{issue_number} -->` followed by a blank line."
        )
        original_content = None
    else:
        existing_plan = ""
        if existing_plan_path:
            with open(existing_plan_path) as f:
                existing_plan = f.read()

        review_feedback = ""
        if review_feedback_file:
            with open(review_feedback_file) as f:
                review_feedback = f.read()

        agent_prompt = (
            f"Use the shipyard-replanner skill.\n\n"
            f"## Issue context\n\n{context}\n\n"
            f"## Existing plan\n\n{existing_plan}\n\n"
            f"## Review feedback (incorporate this)\n\n{review_feedback}\n\n"
            f"Write the updated plan to: {plan_path}\n"
            f"Start the file with `<!-- Related to: #{issue_number} -->` followed by a blank line."
        )
        original_content = existing_plan if existing_plan_path else None

    asyncio.run(run_plan_agent(agent_prompt, cwd, plan_path, original_content))
    _ensure_header(plan_path, issue_number)

    print(plan_path)
