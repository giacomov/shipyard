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


def extract_issue_from_pr_review(event_json: dict[str, Any]) -> int:
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


def _get_pr_branch(repo: str, pr_number: int) -> str:
    """Return the head branch name of a pull request."""
    return gh(["api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".head.ref"]).strip()


def _build_pr_comment_feedback(repo: str, pr_number: int) -> str:
    """Concatenate all conversation comments on a PR into a feedback string."""
    return gh(
        [
            "api",
            f"repos/{repo}/issues/{pr_number}/comments",
            "--jq",
            '[.[] | "### Comment by " + .user.login + "\n" + .body] | join("\n\n")',
        ]
    ).strip()


def _is_plan_branch(branch_name: str) -> bool:
    return branch_name.startswith("shipyard-plan/") or branch_name.startswith("plan/")


def _issue_number_from_plan_branch(branch_name: str) -> int:
    if branch_name.startswith("shipyard-plan/"):
        return int(branch_name.removeprefix("shipyard-plan/i"))
    return int(branch_name.removeprefix("plan/i"))


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

    if "comment" in event_json:
        comment_body = os.environ.get("COMMENT_BODY", "").strip()
        is_pr_comment = bool(event_json.get("issue", {}).get("pull_request"))

        if is_pr_comment and comment_body.startswith("/ship replan"):
            pr_number = event_json["issue"]["number"]
            branch_name = _get_pr_branch(repo, pr_number)
            if not _is_plan_branch(branch_name):
                click.echo(
                    f"Error: /ship replan only valid on shipyard-plan/ branches, got '{branch_name}'.",
                    err=True,
                )
                sys.exit(1)
            issue_number = _issue_number_from_plan_branch(branch_name)
            context = fetch_issue_context(repo, issue_number)
            feedback = _build_pr_comment_feedback(repo, pr_number)

            with open("review-feedback.txt", "w") as f:
                f.write(feedback)
            with open("prompt.txt", "w") as f:
                f.write(
                    f"Issue #{context['issue_number']}: {context['issue_title']}\n\n{context['issue_body']}"
                )

            _set_github_output("has_review", "true")
            _set_github_output("issue_number", str(issue_number))
            _set_github_output("issue_title", context["issue_title"])
            _set_github_output("pr_number", str(pr_number))

        else:
            issue_number = event_json["issue"]["number"]
            issue_title: str = event_json["issue"]["title"]
            issue_body: str = event_json["issue"].get("body") or ""

            with open("prompt.txt", "w") as f:
                f.write(f"Issue #{issue_number}: {issue_title}\n\n{issue_body}")

            _set_github_output("issue_number", str(issue_number))
            _set_github_output("issue_title", issue_title)
            _set_github_output("has_review", "false")

    elif "review" in event_json and event_json["review"]["state"].upper() == "CHANGES_REQUESTED":
        review_body: str = event_json["review"].get("body") or ""
        pr_number = event_json["pull_request"]["number"]
        review_id: int = event_json["review"]["id"]
        branch_name = event_json["pull_request"]["head"]["ref"]

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

            _set_github_output("pr_number", str(pr_number))
            _set_github_output("has_review", "true")

        elif _is_plan_branch(branch_name):
            try:
                issue_number = extract_issue_from_pr_review(event_json)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)

            context = fetch_issue_context(repo, issue_number)

            with open("prompt.txt", "w") as f:
                f.write(
                    f"Issue #{context['issue_number']}: {context['issue_title']}\n\n{context['issue_body']}"
                )

            _set_github_output("issue_number", str(issue_number))
            _set_github_output("issue_title", context["issue_title"])
            _set_github_output("pr_number", str(pr_number))
            _set_github_output("has_review", "true")

        else:
            click.echo(
                f"Error: unrecognised branch prefix '{branch_name}' — "
                "expected 'shipyard-plan/', 'plan/', or 'shipyard/'.",
                err=True,
            )
            sys.exit(1)

    else:
        issue_num_str = os.environ.get("ISSUE_NUMBER", "").strip()
        if not issue_num_str:
            click.echo("Error: unrecognised event type — nothing to do.", err=True)
            sys.exit(1)
        issue_number = int(issue_num_str)
        context = fetch_issue_context(repo, issue_number)
        with open("prompt.txt", "w") as f:
            f.write(
                f"Issue #{context['issue_number']}: {context['issue_title']}\n\n{context['issue_body']}"
            )
        _set_github_output("issue_number", str(issue_number))
        _set_github_output("issue_title", context["issue_title"])
        _set_github_output("has_review", "false")
