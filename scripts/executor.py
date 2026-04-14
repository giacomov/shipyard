#!/usr/bin/env python3
"""Three-agent executor using the Anthropic Agent SDK.

Reads $WORK_JSON (JSON from find_epic_work.py), runs an implementer +
spec reviewer + code quality reviewer for each unblocked issue, then
creates a PR for all successfully implemented issues.

Usage (GitHub Actions):
    WORK_JSON='...' python scripts/executor.py

Usage (local testing):
    python scripts/executor.py --work-json path/to/work.json
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk import AssistantMessage, TextBlock

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


def close_issues_body(issue_numbers: list[int]) -> str:
    """Generate 'Closes #N' lines for a PR body."""
    lines = ["This PR implements the following issues:\n"]
    lines.extend(f"Closes #{n}" for n in issue_numbers)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent SDK
# ---------------------------------------------------------------------------

async def run_agent(prompt: str, options: ClaudeAgentOptions) -> str:
    """Run an agent and return all text output concatenated."""
    output_parts: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
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
# Git helpers
# ---------------------------------------------------------------------------

def git_head_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def git_reset_hard(sha: str) -> None:
    subprocess.run(["git", "reset", "--hard", sha], check=True)


def git_create_and_checkout_branch(branch: str) -> None:
    subprocess.run(["git", "checkout", "-b", branch], check=True)


def git_push_branch(branch: str) -> None:
    subprocess.run(["git", "push", "-u", "origin", branch], check=True)


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a comment on the GitHub issue."""
    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body],
        check=True,
    )


def create_pull_request(repo: str, branch: str, title: str, body: str) -> str:
    """Create PR and return its URL."""
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--repo", repo,
            "--base", "main",
            "--head", branch,
            "--title", title,
            "--body", body,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Three-agent pipeline
# ---------------------------------------------------------------------------

async def run_issue_pipeline(
    issue: IssueWork,
    work: WorkSpec,
    base_sha: str,
    max_retries: int = 1,
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
        f"Repository: {work.repo}\n"
        f"Epic: #{work.epic_number} — {work.epic_title}\n"
        f"{work.epic_body}"
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
            git_reset_hard(base_sha)
            post_issue_comment(
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
                git_reset_hard(base_sha)
                continue
            else:
                git_reset_hard(base_sha)
                post_issue_comment(
                    work.repo, issue.number,
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
                git_reset_hard(base_sha)
                continue
            else:
                git_reset_hard(base_sha)
                post_issue_comment(
                    work.repo, issue.number,
                    f"<!-- shipyard-executor: QUALITY_FAILED -->\n"
                    f"**Code quality review failed after {max_retries + 1} attempt(s)**\n\n"
                    f"<details><summary>Quality reviewer output</summary>\n\n{quality_output}\n\n</details>",
                )
                return False

        # Both reviews passed
        return True

    assert False, "unreachable: all loop iterations terminate via return"


async def run_all_issues(work: WorkSpec) -> dict[int, bool]:
    """Run all issues sequentially. Returns {issue_number: success}."""
    results: dict[int, bool] = {}
    for issue in work.issues:
        print(f"\n── Implementing issue #{issue.number}: {issue.title}")
        base_sha = git_head_sha()
        success = await run_issue_pipeline(issue, work, base_sha=base_sha)
        results[issue.number] = success
        if success:
            print(f"   ✓ Issue #{issue.number} implemented and approved")
        else:
            print(f"   ✗ Issue #{issue.number} failed — commits reset")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-json", type=Path, help="Path to work JSON file")
    args = parser.parse_args()

    if args.work_json:
        raw = args.work_json.read_text()
    else:
        raw = os.environ.get("WORK_JSON")
        if not raw:
            print("Error: $WORK_JSON is not set and --work-json not provided.", file=sys.stderr)
            sys.exit(1)

    data = json.loads(raw)
    work = WorkSpec(
        epic_number=data["epic_number"],
        epic_title=data["epic_title"],
        epic_body=data.get("epic_body", ""),
        repo=data["repo"],
        issues=[IssueWork(**i) for i in data["issues"]],
    )

    # Create a fresh branch for this run
    run_id = os.environ.get("GITHUB_RUN_ID") or str(int(time.time()))
    branch = f"shipyard/epic-{work.epic_number}-run-{run_id}"
    git_create_and_checkout_branch(branch)
    print(f"Branch: {branch}")

    results = asyncio.run(run_all_issues(work))

    successful = [n for n, ok in results.items() if ok]
    failed = [n for n, ok in results.items() if not ok]

    print(f"\n── Results: {len(successful)} succeeded, {len(failed)} failed")

    if not successful:
        print("No issues implemented — skipping PR creation.")
        sys.exit(1)

    git_push_branch(branch)
    pr_title = f"shipyard: implement {len(successful)} issue(s) from epic #{work.epic_number}"
    pr_body = close_issues_body(successful)
    pr_url = create_pull_request(work.repo, branch, pr_title, pr_body)
    print(f"\nPR created: {pr_url}")

    if failed:
        print(f"WARNING: {len(failed)} issue(s) failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
