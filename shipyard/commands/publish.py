#!/usr/bin/env python3
"""shipyard publish-execution — push branch and open PR after execution (CI use only)."""

import json
from pathlib import Path

import click

from shipyard.schemas import SubtaskList
from shipyard.settings import settings
from shipyard.utils.gh import close_issues_body, create_pull_request, resolve_repo
from shipyard.utils.git import push


@click.command("publish-execution")
@click.option("--branch", required=True, help="Branch to push")
@click.option(
    "-i",
    "--input",
    "input_file",
    type=click.Path(exists=True),
    required=True,
    help="Work JSON file (SubtaskList) produced by shipyard find-work",
)
@click.option(
    "--results-file",
    default=settings.results_file,
    type=click.Path(exists=True),
    help="Results JSON written by shipyard execute",
)
@click.option("--base-branch", default=settings.pr_base_branch, help="Base branch for the PR")
def publish_execution(branch: str, input_file: str, results_file: str, base_branch: str) -> None:
    """Push the implementation branch and open a PR."""
    results = json.loads(Path(results_file).read_text())
    successful_task_ids: list[str] = results.get("successful", [])

    if not successful_task_ids:
        print("No successful tasks — skipping push and PR creation.")
        return

    work = SubtaskList.model_validate_json(Path(input_file).read_text())
    repo = resolve_repo()

    successful_issue_numbers = [int(tid) for tid in successful_task_ids]

    push(branch, set_upstream=True)

    pr_title = f"shipyard: implement {len(successful_task_ids)} task(s) from epic #{work.epic_id}"
    pr_body = close_issues_body(successful_issue_numbers)
    pr_url = create_pull_request(repo, branch, pr_title, pr_body, base=base_branch)
    print(f"PR created: {pr_url}")
