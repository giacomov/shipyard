#!/usr/bin/env python3
"""shipyard sync — mirror task JSON to GitHub Issues."""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import click
import pydantic

from shipyard.schemas import Subtask, SubtaskList
from shipyard.settings import settings
from shipyard.utils.gh import gh, resolve_repo
from shipyard.utils.git import checkout_new_branch, push


@dataclass
class IssueRef:
    number: int
    url: str
    database_id: int


def create_issue(repo: str, title: str, body: str, dry_run: bool) -> IssueRef:
    """Create a GitHub issue and return IssueRef with number, url, database_id."""
    if dry_run:
        print(f"  [dry-run] gh issue create: {title}")
        return IssueRef(number=0, url="", database_id=0)
    url = gh(["issue", "create", "--repo", repo, "--title", title, "--body", body])
    m = re.search(r"/issues/(\d+)$", url)
    if not m:
        raise RuntimeError(f"Unexpected gh issue create output: {url!r}")
    number = int(m.group(1))
    owner, repo_name = repo.split("/", 1)
    database_id = int(gh(["api", f"repos/{owner}/{repo_name}/issues/{number}", "-q", ".id"]))
    return IssueRef(number=number, url=url, database_id=database_id)


def add_sub_issue(
    repo: str,
    parent_number: int,
    child_database_id: int,
    child_number: int,
    dry_run: bool,
) -> None:
    """Link child as sub-issue of parent."""
    owner, repo_name = repo.split("/", 1)
    gh(
        [
            "api",
            "--preview",
            "issues",
            f"repos/{owner}/{repo_name}/issues/{parent_number}/sub_issues",
            "--method",
            "POST",
            "-F",
            f"sub_issue_id={child_database_id}",
        ],
        dry_run=dry_run,
        dry_label=f"add #{child_number} as sub-issue of #{parent_number}",
    )


def add_blocked_by(
    repo: str,
    blocked_number: int,
    blocked_database_id: int,
    blocking_number: int,
    blocking_database_id: int,
    dry_run: bool,
) -> None:
    """Mark blocked_number as blocked by blocking_number. Soft-fails on 404."""
    owner, repo_name = repo.split("/", 1)
    try:
        gh(
            [
                "api",
                f"repos/{owner}/{repo_name}/issues/{blocked_number}/dependencies/blocked_by",
                "--method",
                "POST",
                "-F",
                f"issue_id={blocking_database_id}",
            ],
            dry_run=dry_run,
            dry_label=f"mark #{blocked_number} blocked by #{blocking_number}",
        )
    except RuntimeError as e:
        msg = str(e)
        if "404" in msg or "Not Found" in msg:
            print(
                f"   WARNING: dependencies API not available for this repo ({msg.splitlines()[0]})"
            )
        else:
            raise


def ensure_label_exists(repo: str, name: str, color: str, description: str) -> None:
    """Create label if it does not already exist."""
    existing = gh(["label", "list", "--repo", repo, "--json", "name", "--jq", ".[].name"])
    if name in existing.splitlines():
        return
    gh(["label", "create", name, "--repo", repo, "--color", color, "--description", description])


def add_in_progress_label(repo: str, issue_number: int, dry_run: bool) -> None:
    """Ensure 'in-progress' label exists, then apply it to the issue."""
    if not dry_run:
        ensure_label_exists(
            repo,
            settings.epic_status_label,
            settings.epic_label_color,
            "Work is actively being driven by the epic driver",
        )
    gh(
        [
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--add-label",
            settings.epic_status_label,
        ],
        dry_run=dry_run,
        dry_label=f"add in-progress label to #{issue_number}",
    )


def task_body(subtask: Subtask) -> str:
    """Format the GitHub issue body for a Subtask."""
    status_emoji = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}
    emoji = status_emoji.get(subtask.status, "⬜")
    lines = []
    if subtask.description:
        lines.append(subtask.description)
        lines.append("")
    lines.append(f"**Status:** {emoji} `{subtask.status}`")
    if subtask.blocked_by:
        lines.append(f"**Depends on task IDs:** {', '.join(sorted(subtask.blocked_by))}")
    return "\n".join(lines)


def validate(task_list: SubtaskList) -> None:
    """Post-Pydantic validation: non-empty tasks and valid blocked_by references."""
    if not task_list.tasks:
        raise ValueError('Input JSON must have a non-empty "tasks" dict.')
    all_ids = set(task_list.tasks.keys())
    for task_id, subtask in task_list.tasks.items():
        for dep in subtask.blocked_by:
            if dep not in all_ids:
                raise ValueError(f'Task {task_id} has unknown dependency "{dep}".')


def run_sync(task_list: SubtaskList, repo: str, dry_run: bool, skip_label: bool = False) -> int:
    """Main sync logic. Returns exit code (0=success, 1=partial failures)."""
    failures: list[str] = []
    tasks = list(task_list.tasks.values())

    print(f"\nRepository: {repo}")
    print(f"Tasks: {len(tasks)}")
    if dry_run:
        print("Mode: dry-run (no API calls)\n")

    # 1. Create parent epic issue
    print(f'\n── Creating parent issue: "{task_list.title}"')
    try:
        parent = create_issue(
            repo,
            task_list.title,
            task_list.description or f"Task list with {len(tasks)} items.",
            dry_run,
        )
        if not dry_run:
            print(f"   → #{parent.number}")
    except RuntimeError as e:
        print(f"   FAILED: {e}")
        return 1

    # 2. Create one issue per task
    print("\n── Creating task issues")
    issue_map: dict[str, IssueRef] = {}
    for subtask in tasks:
        print(f"   [{subtask.task_id}] {subtask.title}")
        try:
            ref = create_issue(repo, subtask.title, task_body(subtask), dry_run)
            issue_map[subtask.task_id] = ref
            if not dry_run:
                print(f"         → #{ref.number}")
        except RuntimeError as e:
            print(f"         FAILED: {e}")
            failures.append(f"create issue for task {subtask.task_id}: {e}")

    # 3. Link sub-issues to parent
    print("\n── Linking sub-issues to parent")
    for subtask in tasks:
        entry = issue_map.get(subtask.task_id)
        if entry is None:
            continue
        try:
            add_sub_issue(repo, parent.number, entry.database_id, entry.number, dry_run)
        except RuntimeError as e:
            print(f"   FAILED: {e}")
            failures.append(f"sub-issue link for task {subtask.task_id}: {e}")

    # 4. Wire blocked-by edges
    dep_edges = [(subtask.task_id, dep) for subtask in tasks for dep in subtask.blocked_by]
    if dep_edges:
        print("\n── Adding blocked-by relationships")
        for blocked_id, blocking_id in dep_edges:
            blocked = issue_map.get(blocked_id)
            blocking = issue_map.get(blocking_id)
            if not blocked or not blocking:
                continue
            print(
                f"   #{blocked.number if not dry_run else f'({blocked_id})'} blocked by #{blocking.number if not dry_run else f'({blocking_id})'}"
            )
            try:
                add_blocked_by(
                    repo,
                    blocked.number,
                    blocked.database_id,
                    blocking.number,
                    blocking.database_id,
                    dry_run,
                )
            except RuntimeError as e:
                print(f"   FAILED: {e}")
                failures.append(f"blocked-by for {blocked_id}→{blocking_id}: {e}")

    # 5. Add in-progress label to epic
    if not skip_label:
        print("\n── Marking epic as in-progress")
        try:
            add_in_progress_label(repo, parent.number, dry_run)
            if not dry_run:
                print(f'   → added "in-progress" label to #{parent.number}')
        except RuntimeError as e:
            print(f"   WARNING: could not add in-progress label: {e}")
            failures.append(f"add in-progress label: {e}")

    # 6. Create and push epic branch
    epic_branch = f"shipyard/epic-{parent.number}"
    click.echo(f"\n── Creating epic branch: {epic_branch}")
    if not dry_run:
        try:
            checkout_new_branch(epic_branch)
            push(epic_branch, set_upstream=True)
            click.echo(f"   → pushed {epic_branch}")
        except RuntimeError as e:
            click.echo(f"   WARNING: could not create/push epic branch: {e}")
            failures.append(f"create epic branch: {e}")
    else:
        click.echo(f"   [dry-run] Would create and push branch: {epic_branch}")

    # 7. Summary
    print("\n── Summary")
    if not dry_run:
        print(f"   Epic branch:  {epic_branch}")
        print(f"   Parent issue: https://github.com/{repo}/issues/{parent.number}")
        for subtask in tasks:
            entry = issue_map.get(subtask.task_id)
            if entry:
                print(f"   [{subtask.task_id}] {subtask.title[:60]} → #{entry.number}")
    if failures:
        print(f"\n   {len(failures)} failure(s):")
        for f in failures:
            print(f"   • {f}")
        return 1
    print("   All steps completed successfully.")
    return 0


@click.command()
@click.option(
    "-i",
    "--input",
    "input_file",
    type=click.Path(exists=True),
    default=None,
    help="Input tasks.json (default: stdin)",
)
@click.option("--repo", default=None, help="Target repo as owner/repo (default: auto-detect)")
@click.option("--dry-run", is_flag=True, help="Print actions without making API calls")
@click.option(
    "--no-in-progress-label",
    "no_in_progress_label",
    is_flag=True,
    default=False,
    help="Skip adding the in-progress label to the epic issue.",
)
def sync(
    input_file: str | None, repo: str | None, dry_run: bool, no_in_progress_label: bool
) -> None:
    """Sync task JSON to GitHub Issues."""
    if input_file:
        data = json.loads(Path(input_file).read_text())
    else:
        data = json.loads(sys.stdin.read())

    try:
        task_list = SubtaskList.model_validate(data)
    except pydantic.ValidationError as e:
        raise click.ClickException(f"Invalid task JSON: {e}")

    try:
        validate(task_list)
    except ValueError as e:
        raise click.ClickException(str(e))

    resolved_repo = resolve_repo(repo, dry_run)
    exit_code = run_sync(task_list, resolved_repo, dry_run, skip_label=no_in_progress_label)
    if exit_code != 0:
        raise SystemExit(exit_code)
