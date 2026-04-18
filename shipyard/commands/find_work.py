#!/usr/bin/env python3
"""shipyard find-work — find unblocked sub-issues for the current epic (CI use only)."""

import json
import os

import click

from shipyard.schemas import Subtask, SubtaskList
from shipyard.settings import settings
from shipyard.utils.gh import gh, parse_closing_references
from shipyard.utils.gh import set_github_output as set_output

_WORK_JSON_EXCLUDE: dict = {"committed": True, "drafting": True}


def gh_get(path: str) -> dict | list:
    """GET from gh api, return parsed JSON."""
    return json.loads(gh(["api", path]))


def gh_graphql(query: str, variables: dict[str, str | int]) -> dict:
    """Run a GraphQL query. Returns response.data. Raises on errors."""
    var_args = [arg for k, v in variables.items() for arg in ["-F", f"{k}={v}"]]
    result = json.loads(gh(["api", "graphql", "-f", f"query={query}"] + var_args))
    if result.get("errors"):
        raise RuntimeError("; ".join(e["message"] for e in result["errors"]))
    return result["data"]


def resolve_epic_number(
    event: str,
    issue_number: int | None,
    pr_body: str,
    owner: str,
    repo_name: str,
) -> int | None:
    """Return the epic issue number based on the trigger event."""
    if event in ("issues", "workflow_dispatch"):
        return issue_number

    if event == "pull_request":
        closed_numbers = parse_closing_references(pr_body)
        if not closed_numbers:
            print("PR body contains no closing references — nothing to do.")
            return None

        print(f"PR closes: {', '.join(f'#{n}' for n in closed_numbers)}")

        parent_query = """
        query($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                issue(number: $number) {
                    parent {
                        number
                        labels(first: 20) { nodes { name } }
                    }
                }
            }
        }
        """
        for n in closed_numbers:
            try:
                data = gh_graphql(parent_query, {"owner": owner, "repo": repo_name, "number": n})
                parent = data["repository"]["issue"].get("parent")
                if parent:
                    label_names = [lbl["name"] for lbl in parent["labels"]["nodes"]]
                    if settings.epic_status_label in label_names:
                        print(f"Found epic #{parent['number']} via GraphQL parent of #{n}.")
                        return parent["number"]
            except RuntimeError as e:
                print(f"GraphQL parent lookup failed for #{n}: {e}")

        # Fallback: scan open in-progress issues
        print("GraphQL parent lookup found nothing — falling back to label search.")
        repo = f"{owner}/{repo_name}"
        candidates = json.loads(
            gh(
                [
                    "issue",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--label",
                    settings.epic_status_label,
                    "--json",
                    "number",
                    "--limit",
                    "50",
                ]
            )
        )
        for candidate in candidates:
            subs = gh_get(f"repos/{repo}/issues/{candidate['number']}/sub_issues")
            sub_numbers = [s["number"] for s in subs]
            if any(n in sub_numbers for n in closed_numbers):
                print(f"Found epic #{candidate['number']} via sub-issue membership.")
                return candidate["number"]

        print("Could not find an in-progress epic for this PR — nothing to do.")
        return None

    raise RuntimeError(f"Unknown EVENT_NAME: {event!r}")


def find_unblocked_sub_issues(epic_number: int, repo: str) -> list[dict]:
    """Return open sub-issues of epic that have no open blockers."""
    subs = gh_get(f"repos/{repo}/issues/{epic_number}/sub_issues")
    open_subs = [s for s in subs if s["state"] == "open"]
    unblocked = []
    for sub in open_subs:
        blockers = gh_get(f"repos/{repo}/issues/{sub['number']}/dependencies/blocked_by")
        if not any(b["state"] == "open" for b in blockers):
            unblocked.append(sub)
    return unblocked


def build_subtask_list(epic: dict, unblocked: list[dict]) -> SubtaskList:
    """Convert GitHub epic + unblocked issues into a SubtaskList."""
    tasks: dict[str, Subtask] = {}
    for issue in unblocked:
        tid = str(issue["number"])
        tasks[tid] = Subtask(
            task_id=tid,
            title=issue["title"],
            description=issue.get("body") or "",
        )
    return SubtaskList(
        epic_id=str(epic["number"]),
        title=epic["title"],
        description=epic.get("body") or "",
        tasks=tasks,
    )


@click.command("find-work")
def find_work() -> None:
    """Find unblocked sub-issues for the current epic (CI use only)."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    event = os.environ.get("EVENT_NAME")
    issue_num_str = os.environ.get("ISSUE_NUMBER", "")
    pr_body = os.environ.get("PR_BODY", "")

    if not repo:
        raise click.ClickException("GITHUB_REPOSITORY is not set.")
    if not event:
        raise click.ClickException("EVENT_NAME is not set.")

    owner, repo_name = repo.split("/", 1)
    issue_number = int(issue_num_str) if issue_num_str.strip() else None

    if event in ("issues", "workflow_dispatch") and not issue_num_str.strip():
        raise click.ClickException("ISSUE_NUMBER is required for issues/workflow_dispatch events.")

    epic_number = resolve_epic_number(event, issue_number, pr_body, owner, repo_name)
    if epic_number is None:
        set_output("has_work", "false")
        return

    print(f"Epic: #{epic_number}")
    epic_raw = gh_get(f"repos/{repo}/issues/{epic_number}")
    assert isinstance(epic_raw, dict), f"Expected dict from issues API, got {type(epic_raw)}"
    epic: dict = epic_raw
    unblocked = find_unblocked_sub_issues(epic_number, repo)

    if not unblocked:
        print("No unblocked sub-issues — waiting for blockers to resolve.")
        set_output("has_work", "false")
        return

    unblocked_nums = ", ".join(f"#{u['number']}" for u in unblocked)
    print(f"Unblocked: {unblocked_nums}")
    work = build_subtask_list(epic, unblocked)
    set_output("has_work", "true")
    set_output("work_json", work.model_dump_json(exclude=_WORK_JSON_EXCLUDE))
