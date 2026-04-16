#!/usr/bin/env python3
"""shipyard execute — run the three-agent pipeline for unblocked issues (CI use only)."""

import asyncio
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import click
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from shipyard.utils.agent import report_results
from shipyard.utils.gh import post_issue_comment
from shipyard.utils.git import get_head_sha, reset_hard

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class ImplementerStatus(str, Enum):
    DONE = "DONE"
    DONE_WITH_CONCERNS = "DONE_WITH_CONCERNS"
    BLOCKED = "BLOCKED"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"


@dataclass
class IssueWork:
    number: int
    title: str
    body: str


@dataclass
class WorkSpec:
    epic_number: int
    epic_title: str
    epic_body: str
    repo: str
    issues: list[IssueWork]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_implementer_status(output: str) -> ImplementerStatus:
    """Extract status from implementer output. Defaults to BLOCKED if not found.

    Longer/more-specific enum values are checked first to avoid substring collisions
    (e.g. DONE_WITH_CONCERNS must be matched before DONE).
    """
    sorted_statuses = sorted(ImplementerStatus, key=lambda s: len(s.value), reverse=True)
    for line in reversed(output.splitlines()):
        stripped = line.strip().upper()
        for status in sorted_statuses:
            if status.value in stripped:
                return status
    return ImplementerStatus.BLOCKED


def parse_review_verdict(output: str) -> bool:
    """Return True only if output contains the standalone token APPROVED."""
    upper = output.upper()
    if "CHANGES_REQUESTED" in upper:
        return False
    return bool(re.search(r"(?<!NOT )\bAPPROVED\b", upper))


def format_prompt(template: str, **kwargs: str) -> str:
    """Substitute {PLACEHOLDER} values in a prompt template."""
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value)
    return template


# ---------------------------------------------------------------------------
# Agent SDK
# ---------------------------------------------------------------------------


async def run_agent(prompt: str, options: ClaudeAgentOptions) -> str:
    """Run an agent and return all text output concatenated."""
    output_parts: list[str] = []
    async for message in query(prompt=prompt, options=options):
        report_results(message)
        match message:
            case AssistantMessage():
                for block in message.content:
                    match block:
                        case TextBlock():
                            output_parts.append(block.text)
    return "\n".join(output_parts)


def make_agent_options(cwd: str) -> ClaudeAgentOptions:
    """Return ClaudeAgentOptions for CI agents (bypass all permissions)."""
    return ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# Three-agent pipeline
# ---------------------------------------------------------------------------


async def run_issue_pipeline(
    issue: IssueWork,
    work: WorkSpec,
    base_sha: str,
    max_retries: int = 1,
    *,
    reset_fn: Callable[[str], None] = lambda _: None,
    comment_fn: Callable[[str, int, str], None] = lambda *_: None,
) -> bool:
    """Run implementer + spec reviewer + quality reviewer for one issue.

    Returns True if all reviews pass and the issue's commits should be kept.
    Returns False if the issue failed; in that case the git state is reset to base_sha.
    """
    cwd = os.getcwd()
    implementer_tmpl = (PROMPTS_DIR / "implementer.md").read_text()
    spec_tmpl = (PROMPTS_DIR / "spec-reviewer.md").read_text()
    quality_tmpl = (PROMPTS_DIR / "code-quality-reviewer.md").read_text()

    context = (
        f"Repository: {work.repo}\nEpic: #{work.epic_number} — {work.epic_title}\n{work.epic_body}"
    )

    implementer_report = ""
    for attempt in range(max_retries + 1):
        # Build implementer prompt: on retry, append previous reviewer feedback
        extra = ""
        if attempt > 0 and implementer_report:
            extra = f"\n\n## Reviewer Feedback (attempt {attempt})\n\n{implementer_report}"
        prompt = format_prompt(
            implementer_tmpl,
            TASK_DESCRIPTION=issue.body,
            CONTEXT=context + extra,
        )
        implementer_report = await run_agent(prompt, make_agent_options(cwd))
        status = parse_implementer_status(implementer_report)

        if status in (ImplementerStatus.BLOCKED, ImplementerStatus.NEEDS_CONTEXT):
            reset_fn(base_sha)
            comment_fn(
                work.repo,
                issue.number,
                f"<!-- shipyard-executor: {status.value} -->\n"
                f"**Executor halted — implementer reported {status.value}**\n\n"
                f"<details><summary>Agent output</summary>\n\n{implementer_report}\n\n</details>",
            )
            return False

        # Spec review
        spec_prompt = format_prompt(
            spec_tmpl,
            TASK_DESCRIPTION=issue.body,
            IMPLEMENTER_REPORT=implementer_report,
            BASE_SHA=base_sha,
        )
        spec_output = await run_agent(spec_prompt, make_agent_options(cwd))
        spec_approved = parse_review_verdict(spec_output)

        if not spec_approved:
            if attempt < max_retries:
                # Will retry implementer with spec feedback appended
                implementer_report = f"Spec review feedback:\n{spec_output}"
                reset_fn(base_sha)
                continue
            else:
                reset_fn(base_sha)
                comment_fn(
                    work.repo,
                    issue.number,
                    f"<!-- shipyard-executor: SPEC_FAILED -->\n"
                    f"**Spec compliance review failed after {max_retries + 1} attempt(s)**\n\n"
                    f"<details><summary>Spec reviewer output</summary>\n\n{spec_output}\n\n</details>",
                )
                return False

        # Code quality review
        quality_prompt = format_prompt(
            quality_tmpl,
            IMPLEMENTER_REPORT=implementer_report,
            BASE_SHA=base_sha,
        )
        quality_output = await run_agent(quality_prompt, make_agent_options(cwd))
        quality_approved = parse_review_verdict(quality_output)

        if not quality_approved:
            if attempt < max_retries:
                implementer_report = f"Code quality review feedback:\n{quality_output}"
                reset_fn(base_sha)
                continue
            else:
                reset_fn(base_sha)
                comment_fn(
                    work.repo,
                    issue.number,
                    f"<!-- shipyard-executor: QUALITY_FAILED -->\n"
                    f"**Code quality review failed after {max_retries + 1} attempt(s)**\n\n"
                    f"<details><summary>Quality reviewer output</summary>\n\n{quality_output}\n\n</details>",
                )
                return False

        # Both reviews passed
        return True

    assert False, "unreachable: all loop iterations terminate via return"


async def run_all_issues(
    work: WorkSpec,
    *,
    reset_fn: Callable[[str], None] = lambda _: None,
    comment_fn: Callable[[str, int, str], None] = lambda *_: None,
) -> dict[int, bool]:
    """Run all issues sequentially. Returns {issue_number: success}."""
    results: dict[int, bool] = {}
    for issue in work.issues:
        print(f"\n── Implementing issue #{issue.number}: {issue.title}")
        base_sha = get_head_sha()
        success = await run_issue_pipeline(
            issue,
            work,
            base_sha,
            reset_fn=reset_fn,
            comment_fn=comment_fn,
        )
        results[issue.number] = success
        if success:
            print(f"   ✓ Issue #{issue.number} implemented and approved")
        else:
            print(f"   ✗ Issue #{issue.number} failed — commits reset")
    return results


@click.command()
def execute() -> None:
    """Run the three-agent pipeline for unblocked issues (CI use only)."""
    work_json_str = os.environ.get("WORK_JSON")
    if not work_json_str:
        raise click.ClickException("$WORK_JSON is not set.")

    data = json.loads(work_json_str)
    work = WorkSpec(
        epic_number=data["epic_number"],
        epic_title=data["epic_title"],
        epic_body=data.get("epic_body", ""),
        repo=data["repo"],
        issues=[IssueWork(**i) for i in data["issues"]],
    )

    results = asyncio.run(
        run_all_issues(
            work,
            reset_fn=reset_hard,
            comment_fn=post_issue_comment,
        )
    )

    successful = [n for n, ok in results.items() if ok]
    failed = [n for n, ok in results.items() if not ok]

    print(f"\n── Results: {len(successful)} succeeded, {len(failed)} failed")

    Path("shipyard-results.json").write_text(
        json.dumps(
            {
                "successful": successful,
                "failed": failed,
            }
        )
    )

    if failed:
        print(f"WARNING: {len(failed)} issue(s) failed: {failed}")
        raise SystemExit(1)
