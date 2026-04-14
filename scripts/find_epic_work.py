#!/usr/bin/env python3
"""Find the current epic and its unblocked sub-issues for GitHub Actions.

Port of invaders/scripts/find-epic-work.mjs.

Required env vars:
    GH_TOKEN           GitHub token (set automatically in Actions)
    GITHUB_REPOSITORY  owner/repo
    EVENT_NAME         'issues' | 'pull_request' | 'workflow_dispatch'
    ISSUE_NUMBER       issue number (for issues/workflow_dispatch events)
    PR_BODY            PR body text (for pull_request events)

GHA outputs written to $GITHUB_OUTPUT:
    has_work           'true' | 'false'
    work_json          JSON string (only when has_work=true)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def gh(args: list[str]) -> str:
    """Run gh CLI and return trimmed stdout. Raises RuntimeError on error."""
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


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


def set_output(key: str, value: str) -> None:
    """Write key=value to $GITHUB_OUTPUT, or print locally."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        delimiter = f"EOF_{key.upper()}"
        with open(output_file, "a") as f:
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"\n[output] {key}=\n{value}")


def parse_closing_references(pr_body: str) -> list[int]:
    """Extract issue numbers from 'closes/fixes/resolves #N' patterns."""
    pattern = re.compile(r"(?:closes?|fixes?|resolves?)\s+#(\d+)", re.IGNORECASE)
    return [int(m.group(1)) for m in pattern.finditer(pr_body)]


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
                    label_names = [l["name"] for l in parent["labels"]["nodes"]]
                    if "in-progress" in label_names:
                        print(f"Found epic #{parent['number']} via GraphQL parent of #{n}.")
                        return parent["number"]
            except RuntimeError as e:
                print(f"GraphQL parent lookup failed for #{n}: {e}")

        # Fallback: scan open in-progress issues
        print("GraphQL parent lookup found nothing — falling back to label search.")
        repo = f"{owner}/{repo_name}"
        candidates = json.loads(
            gh(["issue", "list", "--repo", repo, "--state", "open",
                "--label", "in-progress", "--json", "number", "--limit", "50"])
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


def build_work_json(epic: dict, unblocked: list[dict], repo: str) -> dict:
    """Build the JSON payload passed to executor.py."""
    return {
        "epic_number": epic["number"],
        "epic_title": epic["title"],
        "epic_body": epic.get("body") or "",
        "repo": repo,
        "issues": [
            {"number": issue["number"], "title": issue["title"], "body": issue.get("body") or ""}
            for issue in unblocked
        ],
    }


def main() -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    event = os.environ.get("EVENT_NAME")
    issue_num_str = os.environ.get("ISSUE_NUMBER", "")
    pr_body = os.environ.get("PR_BODY", "")

    if not repo:
        print("Error: GITHUB_REPOSITORY is not set.", file=sys.stderr)
        sys.exit(1)
    if not event:
        print("Error: EVENT_NAME is not set.", file=sys.stderr)
        sys.exit(1)

    owner, repo_name = repo.split("/", 1)
    issue_number = int(issue_num_str) if issue_num_str.strip() else None

    epic_number = resolve_epic_number(event, issue_number, pr_body, owner, repo_name)
    if epic_number is None:
        set_output("has_work", "false")
        return

    print(f"Epic: #{epic_number}")
    epic = gh_get(f"repos/{repo}/issues/{epic_number}")
    unblocked = find_unblocked_sub_issues(epic_number, repo)

    if not unblocked:
        print("No unblocked sub-issues — waiting for blockers to resolve.")
        set_output("has_work", "false")
        return

    unblocked_nums = ", ".join(f"#{u['number']}" for u in unblocked)
    print(f"Unblocked: {unblocked_nums}")
    work = build_work_json(epic, unblocked, repo)
    set_output("has_work", "true")
    set_output("work_json", json.dumps(work))


if __name__ == "__main__":
    main()
