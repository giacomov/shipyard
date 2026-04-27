#!/usr/bin/env python3
"""Shared GitHub CLI and output helpers used across command modules."""

import os
import re
import subprocess

import click

from shipyard.settings import settings
from shipyard.sim import is_sim_mode

_MUTATING_GH_VERBS: set[tuple[str, str]] = {
    ("issue", "create"),
    ("issue", "comment"),
    ("issue", "edit"),
    ("pr", "create"),
    ("label", "create"),
    ("label", "edit"),
}

_MUTATING_API_METHODS = {"POST", "PATCH", "DELETE", "PUT"}


def _sim_intercept(args: list[str]) -> str | None:
    """Return mock output if this gh call should be intercepted in sim mode, else None."""
    if len(args) >= 2 and tuple(args[:2]) in _MUTATING_GH_VERBS:
        click.echo(f"[sim] gh {' '.join(args)}")
        if args[0] == "issue" and args[1] == "create":
            repo = args[args.index("--repo") + 1] if "--repo" in args else "owner/repo"
            return f"https://github.com/{repo}/issues/999"
        if args[0] == "pr" and args[1] == "create":
            repo = args[args.index("--repo") + 1] if "--repo" in args else "owner/repo"
            return f"https://github.com/{repo}/pull/999"
        return ""

    if args and args[0] == "api":
        if "--method" in args:
            idx = args.index("--method")
            if idx + 1 < len(args) and args[idx + 1].upper() in _MUTATING_API_METHODS:
                click.echo(f"[sim] gh {' '.join(args)}")
                return "{}"
        # Mock database_id fetch used by create_issue after a simulated issue create.
        # Detected by the "-q .id" jq filter pattern (specific to that call site).
        if "-q" in args:
            q_idx = args.index("-q")
            if q_idx + 1 < len(args) and args[q_idx + 1] == ".id":
                click.echo(f"[sim] gh {' '.join(args)}")
                return "999"

    return None


def gh(args: list[str]) -> str:
    """Run a gh CLI command and return trimmed stdout.

    Raises RuntimeError on non-zero exit. In sim mode, write operations are
    intercepted and print [sim] lines instead of executing.
    """
    if is_sim_mode():
        result = _sim_intercept(args)
        if result is not None:
            return result
    proc = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh command failed (exit {proc.returncode}): gh {' '.join(args)}\n{proc.stderr}"
        )
    return proc.stdout.strip()


def resolve_repo(repo_flag: str | None = None) -> str:
    """Return 'owner/repo'. Uses gh repo view if repo_flag is None."""
    if repo_flag:
        return repo_flag
    result = gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
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
