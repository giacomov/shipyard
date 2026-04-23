#!/usr/bin/env python3
"""Shared GitHub CLI and output helpers used across command modules."""

import os
import re
import subprocess

from shipyard.settings import settings


def gh(args: list[str], dry_run: bool = False, dry_label: str = "") -> str:
    """Run a gh CLI command and return trimmed stdout.

    Raises RuntimeError on non-zero exit. In dry_run mode, prints the command and returns "".
    """
    if dry_run:
        label = f"  # {dry_label}" if dry_label else ""
        print(f"  [dry-run] gh {' '.join(args)}{label}")
        return ""
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"gh command failed (exit {result.returncode}): gh {' '.join(args)}\n{result.stderr}"
        )
    return result.stdout.strip()


def resolve_repo(repo_flag: str | None = None, dry_run: bool = False) -> str:
    """Return 'owner/repo'. Uses gh repo view if repo_flag is None."""
    if repo_flag:
        return repo_flag
    result = gh(
        ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], dry_run=dry_run
    )
    if not result:
        return "<owner>/<repo>"
    return result


def set_github_output(key: str, value: str) -> None:
    """Write key=value to $GITHUB_OUTPUT (heredoc format) or print locally if unset."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        delimiter = f"EOF_{key.upper()}"
        with open(output_file, "a") as f:
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"\n[output] {key}=\n{value}")


def parse_closing_references(body: str) -> list[int]:
    """Extract issue numbers from 'closes/fixes/resolves #N' patterns (plural forms included)."""
    pattern = re.compile(r"(?:closes?|fixes?|resolves?)\s+#(\d+)", re.IGNORECASE)
    return [int(m.group(1)) for m in pattern.finditer(body)]


def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a comment on a GitHub issue."""
    gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])


def create_pull_request(
    repo: str, branch: str, title: str, body: str, base: str = settings.pr_base_branch
) -> str:
    """Create a PR and return its URL."""
    return gh(
        [
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
    )


def close_issues_body(issue_numbers: list[int]) -> str:
    """Generate 'Closes #N' lines for a PR body."""
    lines = ["This PR implements the following issues:\n"]
    lines.extend(f"Closes #{n}" for n in issue_numbers)
    return "\n".join(lines)
