#!/usr/bin/env python3
"""shipyard execute — run the three-agent pipeline for unblocked issues (CI use only)."""

import asyncio
import json
from collections.abc import Callable
from importlib.resources import files as _res_files
from pathlib import Path

import click
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from shipyard.schemas import Subtask, SubtaskList
from shipyard.settings import EffortLevel, settings
from shipyard.utils.agent import get_sdk_client, receive_from_client
from shipyard.utils.gh import post_issue_comment, resolve_repo
from shipyard.utils.git import get_head_sha, reset_hard

_system_prompt = _res_files("shipyard.data.prompts").joinpath("system-prompt.md").read_text()


async def run_issue_pipeline(
    task: Subtask,
    work: SubtaskList,
    base_sha: str,
    max_retries: int = 1,
    *,
    reset_fn: Callable[[str], None] = lambda _: None,
    comment_fn: Callable[[str, int, str], None] = lambda *_: None,
    model: str,
    effort: EffortLevel,
) -> bool:
    """Run implementer + spec reviewer + quality reviewer for one task.

    Returns True if all reviews pass and the task's commits should be kept.
    Returns False if the task failed; in that case the git state is reset to base_sha.
    """
    try:
        return await _run_issue_pipeline_inner(
            task, work, base_sha, max_retries, model=model, effort=effort
        )
    except Exception as exc:
        click.echo(f"Task {task.task_id} failed: {exc}", err=True)
        try:
            reset_fn(base_sha)
        except Exception as reset_exc:
            click.echo(f"Failed to reset to {base_sha}: {reset_exc}", err=True)
        try:
            comment_body = (
                f"<!-- shipyard-executor: pipeline-failure -->\n"
                f"Shipyard pipeline failed for task {task.task_id}: {task.title}\n\n"
                f"<details><summary>Error</summary>\n\n```\n{exc}\n```\n\n</details>"
            )
            comment_fn("", int(task.task_id), comment_body)
        except Exception as comment_exc:
            click.echo(f"Failed to post failure comment: {comment_exc}", err=True)
        return False


async def _run_issue_pipeline_inner(
    task: Subtask,
    work: SubtaskList,
    base_sha: str,
    max_retries: int = 1,
    *,
    model: str,
    effort: EffortLevel,
) -> bool:
    """Inner pipeline logic, separated so exceptions propagate to the caller."""

    tasks_context = [
        f"- **Task {t.task_id}: {t.title}** [current task]"
        if t.task_id == task.task_id
        else f"- Task {t.task_id}: {t.title}"
        for t in work.tasks.values()
    ]

    task_context = (
        f"## This Task\n\n"
        f"Task {task.task_id}: {task.title}\n\n{task.description}\n\n"
        f"## The rest of the plan\n\n"
        f"This task is part of a larger plan:\n\n"
        + "\n".join(tasks_context)
        + "\n\nNOTE: some of the other tasks in the plan might have been already accomplished."
    )

    review_context = (
        f"{task_context}\n\n"
        f"## Code to review\n\n"
        f"Run the following to see what was changed:\n\n"
        f"```bash\ngit diff --stat {base_sha}..HEAD\ngit diff {base_sha}..HEAD\n```\n\n"
        f"Focus your review ONLY on these changes — do not review pre-existing code."
    )

    options = ClaudeAgentOptions(
        permission_mode="dontAsk",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Monitor", "Grep", "Glob", "Agent"],
        system_prompt=_system_prompt,
        setting_sources=["project"],
        model=model,
        effort=effort,
        agents={
            "spec_reviewer": AgentDefinition(
                description="Expert spec reviewer specialist. Verifies against the spec and provide feedback.",
                prompt="Use the shipyard-spec-reviewer skill.",
                tools=["Bash", "Read", "Grep", "Glob"],
                model=settings.review_model,
                effort=settings.review_effort,
            ),
            "code_quality_reviewer": AgentDefinition(
                description="Expert code quality reviewer specialist. Reviews the code for quality and provide feedback.",
                prompt="Use the shipyard-code-quality-reviewer skill.",
                tools=["Bash", "Read", "Grep", "Glob"],
                model=settings.review_model,
                effort=settings.review_effort,
            ),
        },
    )

    async with get_sdk_client(options) as client:
        # Implement
        await client.query(f"Use the shipyard-implementer skill.\n\n{task_context}")

        await receive_from_client(client)

        await client.query(
            "Now stage and commit your changes, without pushing yet. Make sure to include everything you changed."
        )

        await receive_from_client(client)

        # Review spec
        await client.query(
            f"Now run the spec reviewer agent to review the implementation. "
            f"Pass it this context:\n\n{review_context}\n\n"
            f"If the implementation does not meet the spec, fix the issues and re-run the spec reviewer "
            f"until the implementation meets the spec."
        )

        await receive_from_client(client)

        # Review code quality
        await client.query(
            f"Now run the code quality reviewer agent to review the implementation. "
            f"Pass it this context:\n\n{review_context}\n\n"
            f"If the implementation does not meet the code quality bar, fix the issues and re-run the "
            f"code quality reviewer until the implementation meets the code quality bar."
        )

        await receive_from_client(client)

        # Run the tests
        await client.query(
            "If you changed any testable code, make sure there are tests for it, and run the tests until they pass."
        )

        await receive_from_client(client)

    return True


async def run_all_issues(
    work: SubtaskList,
    *,
    reset_fn: Callable[[str], None] = lambda _: None,
    comment_fn: Callable[[str, int, str], None] = lambda *_: None,
    model: str,
    effort: EffortLevel,
) -> dict[str, list[str]]:
    """Run all tasks sequentially. Returns {"successful": [...], "failed": [...]}."""
    successful: list[str] = []
    failed: list[str] = []

    for task in work.tasks.values():
        print(f"\n── Implementing task {task.task_id}: {task.title}")

        base_sha = get_head_sha()

        ok = await run_issue_pipeline(
            task,
            work,
            base_sha,
            settings.implementer_max_retries,
            reset_fn=reset_fn,
            comment_fn=comment_fn,
            model=model,
            effort=effort,
        )

        if ok:
            successful.append(task.task_id)
            click.echo(f"Task {task.task_id} completed successfully.")
        else:
            failed.append(task.task_id)
            click.echo(f"Task {task.task_id} failed.")

    return {"successful": successful, "failed": failed}


@click.command()
@click.option(
    "-i",
    "--input",
    "input_file",
    type=click.Path(exists=True),
    default=None,
    help="Work JSON file (SubtaskList) produced by shipyard find-work",
)
@click.option(
    "--review-feedback-file",
    type=click.Path(exists=True),
    default=None,
    help="Review feedback file (revision mode)",
)
@click.option(
    "--prompt-file",
    type=click.Path(exists=True),
    default=None,
    help="Original task context file (revision mode)",
)
def execute(
    input_file: str | None,
    review_feedback_file: str | None,
    prompt_file: str | None,
) -> None:
    """Run the three-agent pipeline for unblocked tasks.

    Normal mode: pass -i with a work JSON file.
    Revision mode: pass --review-feedback-file and --prompt-file to address PR review feedback.
    """
    revision_mode = review_feedback_file is not None or prompt_file is not None

    if revision_mode and input_file is not None:
        raise click.UsageError("Cannot combine -i with --review-feedback-file / --prompt-file.")
    if revision_mode and (review_feedback_file is None or prompt_file is None):
        raise click.UsageError(
            "--review-feedback-file and --prompt-file must both be provided for revision mode."
        )
    if not revision_mode and input_file is None:
        raise click.UsageError(
            "Provide -i (normal mode) or --review-feedback-file + --prompt-file (revision mode)."
        )

    if revision_mode:
        assert review_feedback_file is not None and prompt_file is not None
        original_context = Path(prompt_file).read_text()
        review_feedback = Path(review_feedback_file).read_text()

        description = (
            f"## Original requirements\n\n{original_context}\n\n"
            f"## Review feedback to address\n\n{review_feedback}"
        )
        task = Subtask(
            task_id="revision",
            title="Address PR review feedback",
            description=description,
        )
        work = SubtaskList(
            title="PR revision",
            description="",
            tasks={"revision": task},
        )

        results = asyncio.run(
            run_all_issues(
                work,
                reset_fn=reset_hard,
                model=settings.revision_model,
                effort=settings.revision_effort,
            )
        )

        if results["failed"]:
            raise SystemExit(1)
    else:
        assert input_file is not None
        work = SubtaskList.model_validate_json(Path(input_file).read_text())
        repo = resolve_repo()

        results = asyncio.run(
            run_all_issues(
                work,
                reset_fn=reset_hard,
                comment_fn=lambda _, n, body: post_issue_comment(repo, n, body),
                model=settings.execution_model,
                effort=settings.execution_effort,
            )
        )

        Path(settings.results_file).write_text(json.dumps(results, indent=2))
        click.echo(f"Results written to {settings.results_file}")

        if results["failed"]:
            raise SystemExit(1)
