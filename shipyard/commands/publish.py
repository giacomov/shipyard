#!/usr/bin/env python3
"""shipyard publish-execution — push branch and open PR after execution (CI use only)."""

import json
import os
from pathlib import Path

import click

from shipyard.utils.gh import close_issues_body, create_pull_request
from shipyard.utils.git import push


@click.command("publish-execution")
@click.option("--branch", required=True, help="Branch to push")
@click.option(
    "--results-file",
    default="shipyard-results.json",
    type=click.Path(exists=True),
    help="Results JSON written by shipyard execute",
)
def publish_execution(branch: str, results_file: str) -> None:
    """Push the implementation branch and open a PR (CI use only)."""
    work_json_str = os.environ.get("WORK_JSON")
    if not work_json_str:
        raise click.ClickException("$WORK_JSON is not set.")

    results = json.loads(Path(results_file).read_text())
    successful: list[int] = results.get("successful", [])

    if not successful:
        print("No successful issues — skipping push and PR creation.")
        return

    work = json.loads(work_json_str)
    repo: str = work["repo"]
    epic_number: int = work["epic_number"]

    push(branch, set_upstream=True)

    pr_title = f"shipyard: implement {len(successful)} issue(s) from epic #{epic_number}"
    pr_body = close_issues_body(successful)
    pr_url = create_pull_request(repo, branch, pr_title, pr_body)
    print(f"PR created: {pr_url}")
