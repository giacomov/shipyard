#!/usr/bin/env python3
"""shipyard update-docs — run the documentation agent after an epic completes (CI use only)."""

import asyncio
from importlib.resources import files as _res_files

import click
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, ClaudeSDKClient

from shipyard.settings import settings
from shipyard.utils.agent import receive_from_client

_system_prompt = _res_files("shipyard.data.prompts").joinpath("system-prompt.md").read_text()


async def _run_update_docs(base_sha: str) -> None:
    options = ClaudeAgentOptions(
        permission_mode="dontAsk",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Monitor", "Grep", "Glob", "Agent"],
        system_prompt=_system_prompt,
        setting_sources=["project"],
        model=settings.doc_model,
        effort=settings.doc_effort,
        agents={
            "doc_verifier": AgentDefinition(
                description="Documentation verifier. Reviews documentation changes for accuracy and completeness against the code diff, then reports issues or LGTM.",
                prompt="Use the shipyard-doc-verifier skill.",
                tools=["Bash", "Read", "Grep", "Glob"],
                model=settings.doc_review_model,
                effort=settings.doc_review_effort,
            ),
        },
    )

    async with ClaudeSDKClient(options=options) as client:
        # Write/update documentation
        await client.query(
            f"Use the shipyard-doc-agent skill.\n\n"
            f"Focus your work on files that recently changed:\n\n"
            f"```bash\ngit diff --stat {base_sha}..HEAD\ngit diff {base_sha}..HEAD\n```"
        )
        await receive_from_client(client)

        # Stage and commit doc changes
        await client.query(
            "Stage and commit all documentation changes you made, without pushing yet."
        )
        await receive_from_client(client)

        # Verify and iterate until the verifier has no more feedback
        await client.query(
            "Run the doc_verifier sub-agent to review your documentation changes. "
            "If it reports any issues, fix them, commit the fixes, and re-run the verifier. "
            "Keep iterating until the verifier outputs LGTM."
        )
        await receive_from_client(client)


@click.command()
@click.option(
    "--base-sha",
    required=True,
    help="Git SHA of main at the point where the epic branch diverged (used to compute the full epic diff)",
)
def update_docs(base_sha: str) -> None:
    """Update documentation to reflect all changes made across an epic.

    Runs the doc agent against the cumulative diff since BASE_SHA, then verifies
    the result with a reviewer sub-agent, iterating until the reviewer is satisfied.
    CI use only — invoke after all sub-issues in an epic have been implemented.
    """
    asyncio.run(_run_update_docs(base_sha))
