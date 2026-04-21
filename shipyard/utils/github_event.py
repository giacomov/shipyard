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


def fetch_review_inline_comments(repo: str, pr_number: int, review_id: int) -> list[dict[str, Any]]:
    """Return inline comments for a specific review as a list of dicts with path, body, diff_hunk."""
    raw = gh(["api", f"/repos/{repo}/pulls/{pr_number}/reviews/{review_id}/comments"])
    comments: list[dict[str, Any]] = json.loads(raw)
    return [
        {"path": c.get("path", ""), "body": c.get("body", ""), "diff_hunk": c.get("diff_hunk", "")}
        for c in comments
    ]


def build_review_feedback(review_body: str, inline_comments: list[dict[str, Any]]) -> str:
    """Combine review body and inline comments into a single feedback string."""
    parts: list[str] = []
    if review_body.strip():
        parts.append(f"Review summary:\n{review_body.strip()}")
    for c in inline_comments:
        header = f"Inline comment on {c['path']}:"
        hunk = f"```\n{c['diff_hunk']}\n```" if c["diff_hunk"] else ""
        body = c["body"].strip()
        parts.append("\n".join(filter(None, [header, hunk, body])))
    return "\n\n".join(parts)


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
        review_id: int = event_json["review"]["id"]
        branch_name: str = event_json["pull_request"]["head"]["ref"]

        inline_comments = fetch_review_inline_comments(repo, pr_number, review_id)
        feedback = build_review_feedback(review_body, inline_comments)

        with open("review-feedback.txt", "w") as f:
            f.write(feedback)

        if branch_name.startswith("shipyard/"):
            issue_refs = _parse_closing_references(
                event_json.get("pull_request", {}).get("body") or ""
            )
            if not issue_refs:
                click.echo(
                    "Error: no closing references found in implementation PR body.", err=True
                )
                sys.exit(1)

            contexts = [fetch_issue_context(repo, n) for n in issue_refs]
            prompt_parts = [
                f"Issue #{c['issue_number']}: {c['issue_title']}\n\n{c['issue_body']}"
                for c in contexts
            ]
            with open("prompt.txt", "w") as f:
                f.write("\n\n---\n\n".join(prompt_parts))

            _set_github_output("review_target", "implementation")
            _set_github_output("branch_name", branch_name)
            _set_github_output("pr_number", str(pr_number))
            _set_github_output("has_review", "true")

        elif branch_name.startswith("plan/"):
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

            _set_github_output("review_target", "plan")
            _set_github_output("issue_number", str(issue_number))
            _set_github_output("issue_title", context["issue_title"])
            _set_github_output("pr_number", str(pr_number))
            _set_github_output("has_review", "true")

        else:
            click.echo(
                f"Error: unrecognised branch prefix '{branch_name}' — "
                "expected 'plan/' or 'shipyard/'.",
                err=True,
            )
            sys.exit(1)

    else:
        click.echo("Error: unrecognised event type or label — nothing to do.", err=True)
        sys.exit(1)
