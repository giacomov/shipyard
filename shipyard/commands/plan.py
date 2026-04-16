#!/usr/bin/env python3
"""shipyard plan — generate or update an implementation plan for a GitHub issue."""

import asyncio
import os

import click
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query


async def run_plan_agent(prompt: str, cwd: str) -> str:
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep"],
        cwd=cwd,
    )
    output_parts: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    output_parts.append(block.text)
    return "\n".join(output_parts)


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

    if pr_number is None:
        agent_prompt = (
            f"You are a software architect. Based on the following issue context, "
            f"produce a detailed, structured implementation plan in Markdown.\n\n"
            f"{context}"
        )
        plan_content_raw = asyncio.run(run_plan_agent(agent_prompt, cwd))

        header = f"<!-- Related to: #{issue_number} -->\n\n"
        plan_content = header + plan_content_raw

        os.makedirs("plans", exist_ok=True)
        plan_path = f"plans/i{issue_number}.md"
        with open(plan_path, "w") as f:
            f.write(plan_content)
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
            f"You are a software architect revising an implementation plan based on review feedback.\n\n"
            f"ORIGINAL ISSUE CONTEXT:\n{context}\n\n"
            f"EXISTING PLAN:\n{existing_plan}\n\n"
            f"REVIEW FEEDBACK (incorporate this):\n{review_feedback}\n\n"
            f"Produce an updated, complete implementation plan in Markdown."
        )
        plan_content_raw = asyncio.run(run_plan_agent(agent_prompt, cwd))

        header = f"<!-- Related to: #{issue_number} -->\n\n"
        plan_content = header + plan_content_raw

        os.makedirs("plans", exist_ok=True)
        plan_path = f"plans/i{issue_number}.md"
        with open(plan_path, "w") as f:
            f.write(plan_content)

    print(plan_path)
