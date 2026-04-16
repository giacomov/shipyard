#!/usr/bin/env python3
"""shipyard extract-github-event — read a GitHub Actions event JSON and write structured outputs."""

import json
import os
import sys
from typing import Any

import click

from shipyard.utils.gh import gh
from shipyard.utils.gh import parse_closing_references as _parse_closing_references
from shipyard.utils.gh import set_github_output as _set_github_output


def parse_github_event(event_json: dict[str, Any]) -> tuple[int, str]:
    """
    Returns (issue_number, repo).
    - issue_number: from event_json["issue"]["number"] for issues events,
                    or derived from PR body for pull_request_review events
    - repo: from os.environ["GITHUB_REPOSITORY"]
    For issues.labeled events: event_json["issue"]["number"]
    For pull_request_review events: parse PR body via _parse_closing_references,
      return first result
    Raises ValueError if cannot determine issue number.
    """
    repo = os.environ["GITHUB_REPOSITORY"]

    if "issue" in event_json:
        return event_json["issue"]["number"], repo

    if "review" in event_json:
        pr_body = event_json.get("pull_request", {}).get("body") or ""
        refs = _parse_closing_references(pr_body)
        if not refs:
            raise ValueError("pull_request_review event: no closing references found in PR body.")
        return refs[0], repo

    raise ValueError("Cannot determine issue number from event JSON.")


def fetch_issue_context(repo: str, issue_number: int) -> dict[str, Any]:
    """
    Returns dict with keys: issue_number, issue_title, issue_body, repo
    Uses: gh issue view <N> --repo <repo> --json number,title,body
    Parses JSON output.
    """
    raw = gh(["issue", "view", str(issue_number), "--repo", repo, "--json", "number,title,body"])
    data = json.loads(raw)
    return {
        "issue_number": data["number"],
        "issue_title": data["title"],
        "issue_body": data.get("body") or "",
        "repo": repo,
    }


def extract_issue_from_pr_review(event_json: dict[str, Any], repo: str) -> int:
    """
    Parses PR body from event_json["pull_request"]["body"]
    Uses _parse_closing_references() to find Closes #N
    Returns first issue number found.
    Raises ValueError if no closing references found.
    """
    pr_body = event_json.get("pull_request", {}).get("body") or ""
    refs = _parse_closing_references(pr_body)
    if not refs:
        raise ValueError("No closing references found in PR body.")
    return refs[0]


@click.command()
def extract_github_event() -> None:
    """Extract GitHub event context and write to GITHUB_OUTPUT."""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        click.echo("Error: GITHUB_EVENT_PATH is not set.", err=True)
        sys.exit(1)

    with open(event_path) as f:
        event_json: dict[str, Any] = json.load(f)

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        click.echo("Error: GITHUB_REPOSITORY is not set.", err=True)
        sys.exit(1)

    if "issue" in event_json and event_json.get("label", {}).get("name") == "plan":
        issue_number: int = event_json["issue"]["number"]
        issue_title: str = event_json["issue"]["title"]
        issue_body: str = event_json["issue"].get("body") or ""

        with open("prompt.txt", "w") as f:
            f.write(f"Issue #{issue_number}: {issue_title}\n\n{issue_body}")

        _set_github_output("issue_number", str(issue_number))
        _set_github_output("issue_title", issue_title)
        _set_github_output("has_review", "false")

    elif "review" in event_json and event_json["review"]["state"].upper() == "CHANGES_REQUESTED":
        review_body: str = event_json["review"].get("body") or ""
        pr_number: int = event_json["pull_request"]["number"]

        try:
            issue_number = extract_issue_from_pr_review(event_json, repo)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        context = fetch_issue_context(repo, issue_number)

        with open("prompt.txt", "w") as f:
            f.write(
                f"Issue #{context['issue_number']}: {context['issue_title']}\n\n{context['issue_body']}"
            )

        with open("review-feedback.txt", "w") as f:
            f.write(review_body)

        _set_github_output("issue_number", str(issue_number))
        _set_github_output("issue_title", context["issue_title"])
        _set_github_output("pr_number", str(pr_number))
        _set_github_output("has_review", "true")

    else:
        click.echo("Error: unrecognised event type or label — nothing to do.", err=True)
        sys.exit(1)
