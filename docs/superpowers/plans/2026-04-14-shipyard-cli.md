# Shipyard CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Shipyard's standalone scripts into an installable `shipyard` Python CLI with click subcommands, bundled workflow template, and a clean `shipyard/` package layout.

**Architecture:** The four scripts in `scripts/` move into `shipyard/commands/` as click commands; prompts move to `shipyard/prompts/`; a bundled `shipyard/templates/epic-driver.yml` is copied into user repos by `shipyard init`. A thin `shipyard/cli.py` click group wires all commands together and is exposed as the `shipyard` entry point via `pyproject.toml`.

**Tech Stack:** Python 3.12, click>=8.0, pytest + click.testing.CliRunner, importlib.resources

---

## File Map

| File | Action | Notes |
|---|---|---|
| `shipyard/__init__.py` | Create | Empty |
| `shipyard/cli.py` | Create | Click group entry point |
| `shipyard/commands/__init__.py` | Create | Empty |
| `shipyard/commands/tasks.py` | Create | Was `scripts/plan_to_tasks.py` |
| `shipyard/commands/sync.py` | Create | Was `scripts/sync_to_github.py` |
| `shipyard/commands/find_work.py` | Create | Was `scripts/find_epic_work.py` |
| `shipyard/commands/execute.py` | Create | Was `scripts/executor.py` |
| `shipyard/commands/init.py` | Create | New command |
| `shipyard/prompts/` | Create | Was `prompts/` at root |
| `shipyard/templates/epic-driver.yml` | Create | Bundled workflow template |
| `pyproject.toml` | Modify | Add click dep, entry point, package-data |
| `tests/test_scaffolding.py` | Rewrite | Test new package structure |
| `tests/test_plan_to_tasks.py` | Modify | Update imports |
| `tests/test_sync_to_github.py` | Modify | Update imports + patches |
| `tests/test_find_epic_work.py` | Modify | Update imports + patches |
| `tests/test_executor.py` | Modify | Update imports + patches |
| `tests/test_commands_tasks.py` | Create | CliRunner tests for `tasks` |
| `tests/test_commands_sync.py` | Create | CliRunner tests for `sync` |
| `tests/test_commands_find_work.py` | Create | CliRunner test for `find-work` |
| `tests/test_commands_init.py` | Create | CliRunner tests for `init` |
| `tests/test_workflow.py` | Modify | Add template assertions |
| `.github/workflows/epic-driver.yml` | Modify | Dogfood: use CLI commands |
| `scripts/` | Delete | In Task 8 after all tests pass |

---

### Task 1: Package skeleton and pyproject.toml

**Depends on:** (none)

**Files:**
- Create: `shipyard/__init__.py`
- Create: `shipyard/commands/__init__.py`
- Modify: `pyproject.toml`
- Rewrite: `tests/test_scaffolding.py`

- [ ] **Step 1: Write the failing test**

Replace `tests/test_scaffolding.py` with:

```python
import importlib
from pathlib import Path


def test_shipyard_package_importable():
    mod = importlib.import_module("shipyard")
    assert mod is not None


def test_shipyard_commands_package_importable():
    mod = importlib.import_module("shipyard.commands")
    assert mod is not None


def test_required_files_exist():
    root = Path(__file__).parent.parent
    assert (root / "pyproject.toml").exists()
    assert (root / "requirements.txt").exists()
    assert (root / "tests" / "fixtures").is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scaffolding.py -v
```

Expected: `test_shipyard_package_importable` and `test_shipyard_commands_package_importable` fail with `ModuleNotFoundError`.

- [ ] **Step 3: Create the package skeleton**

Create `shipyard/__init__.py` (empty):
```python
```

Create `shipyard/commands/__init__.py` (empty):
```python
```

- [ ] **Step 4: Update pyproject.toml**

Replace `pyproject.toml` with:

```toml
[project]
name = "shipyard"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "claude-agent-sdk>=0.1.0",
    "click>=8.0",
]

[project.scripts]
shipyard = "shipyard.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pyyaml>=6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["shipyard*"]

[tool.setuptools.package-data]
shipyard = ["templates/*.yml", "prompts/*.md"]
```

- [ ] **Step 5: Reinstall the package**

```bash
pip install -e ".[dev]"
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_scaffolding.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 7: Verify existing tests still pass**

```bash
pytest tests/ -v
```

Expected: all 42 existing tests still pass (scripts/ still importable).

- [ ] **Step 8: Commit**

```bash
git add shipyard/__init__.py shipyard/commands/__init__.py pyproject.toml tests/test_scaffolding.py
git commit -m "feat: add shipyard package skeleton and update pyproject.toml"
```

---

### Task 2: `shipyard tasks` command

**Depends on:** Task 1

**Files:**
- Create: `shipyard/commands/tasks.py`
- Modify: `tests/test_plan_to_tasks.py`
- Create: `tests/test_commands_tasks.py`

- [ ] **Step 1: Write the failing CliRunner tests**

Create `tests/test_commands_tasks.py`:

```python
import json
from pathlib import Path

from click.testing import CliRunner

from shipyard.commands.tasks import tasks

FIXTURES = Path(__file__).parent / "fixtures"


def test_tasks_reads_stdin_outputs_json():
    runner = CliRunner()
    plan_text = "# My Plan\n\n**Goal:** Do X.\n\n### Task 1: Alpha\n\n**Depends on:** (none)\n\nDo alpha.\n"
    result = runner.invoke(tasks, input=plan_text)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "My Plan"
    assert len(data["tasks"]) == 1


def test_tasks_reads_file_with_input_flag(tmp_path):
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text(
        "# My Plan\n\n**Goal:** Do X.\n\n### Task 1: Alpha\n\n**Depends on:** (none)\n\nDo alpha.\n"
    )
    result = runner.invoke(tasks, ["-i", str(plan_file)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "My Plan"


def test_tasks_writes_output_file(tmp_path):
    runner = CliRunner()
    plan_text = "# P\n\n**Goal:** X.\n\n### Task 1: A\n\n**Depends on:** (none)\n\nDesc.\n"
    out = tmp_path / "out.json"
    result = runner.invoke(tasks, ["-o", str(out)], input=plan_text)
    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert "tasks" in data


def test_tasks_exits_nonzero_on_bad_dependency():
    runner = CliRunner()
    plan_text = "# P\n\n**Goal:** X.\n\n### Task 1: A\n\n**Depends on:** Task 99\n\nDesc.\n"
    result = runner.invoke(tasks, input=plan_text)
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_tasks.py -v
```

Expected: all 4 tests fail with `ImportError` (module doesn't exist yet).

- [ ] **Step 3: Create `shipyard/commands/tasks.py`**

```python
#!/usr/bin/env python3
"""shipyard tasks — parse a markdown plan into task JSON."""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click


@dataclass
class ParsedTask:
    id: str
    subject: str
    description: str
    status: str = "pending"
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ParsedPlan:
    title: str
    body: str
    tasks: list[ParsedTask]


def parse_plan(text: str) -> ParsedPlan:
    """Parse markdown plan text into a ParsedPlan."""
    title = _parse_title(text)
    body = _parse_goal(text)
    task_blocks = _split_task_blocks(text)
    raw_tasks = []
    for block in task_blocks:
        m = re.match(r"^### Task (\d+):\s*(.+)$", block, re.MULTILINE)
        if not m:
            continue
        task_id = m.group(1)
        raw_tasks.append((task_id, m.group(2).strip(), block))

    tasks_list = [_parse_task_block(task_id, subject, block)
                  for task_id, subject, block in raw_tasks]
    return ParsedPlan(title=title, body=body, tasks=tasks_list)


def _parse_title(text: str) -> str:
    m = re.search(r"^# (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else "Implementation Plan"


def _parse_goal(text: str) -> str:
    m = re.search(r"^\*\*Goal:\*\*\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _split_task_blocks(text: str) -> list[str]:
    """Split on '### Task N:' boundaries (ignores those inside code fences)."""
    lines = text.split("\n")
    in_fence = False
    char_pos = 0
    char_positions: list[int] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"^### Task \d+:", line):
            char_positions.append(char_pos)
        char_pos += len(line) + 1

    if not char_positions:
        return []

    blocks = []
    for i, start in enumerate(char_positions):
        end = char_positions[i + 1] if i + 1 < len(char_positions) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _parse_task_block(task_id: str, subject: str, block: str) -> ParsedTask:
    deps = _parse_depends_on(block)
    description = _extract_description(block)
    return ParsedTask(id=task_id, subject=subject, description=description, dependencies=deps)


def _parse_depends_on(block: str) -> list[str]:
    """Extract dependency ids from a '**Depends on:**' line."""
    m = re.search(r"^\*\*Depends on:\*\*\s*(.+)$", block, re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw.lower() in ("(none)", "none", ""):
        return []
    numbers = re.findall(r"Task\s+(\d+)", raw, re.IGNORECASE)
    if not numbers:
        return []
    return numbers


def _extract_description(block: str) -> str:
    """Remove the task header and **Depends on:** line from the block."""
    lines = block.splitlines()
    filtered = []
    skip_next_blank = False
    for line in lines:
        if re.match(r"^### Task \d+:", line):
            skip_next_blank = True
            continue
        if re.match(r"^\*\*Depends on:\*\*", line):
            skip_next_blank = True
            continue
        if skip_next_blank and line.strip() == "":
            skip_next_blank = False
            continue
        skip_next_blank = False
        filtered.append(line)
    return "\n".join(filtered).strip()


def validate_plan(plan: ParsedPlan) -> None:
    """Raise ValueError if any dependency id is not a known task id."""
    known_ids = {t.id for t in plan.tasks}
    for task in plan.tasks:
        for dep in task.dependencies:
            if dep not in known_ids:
                raise ValueError(
                    f"Task {task.id} has unknown dependency 'Task {dep}'. "
                    f"Known task ids: {sorted(known_ids)}"
                )


def plan_to_tasks_dict(plan: ParsedPlan) -> dict[str, object]:
    """Convert ParsedPlan to the tasks.json dict structure."""
    return {
        "title": plan.title,
        "body": plan.body,
        "tasks": [
            {
                "id": t.id,
                "subject": t.subject,
                "description": t.description,
                "status": t.status,
                "dependencies": t.dependencies,
            }
            for t in plan.tasks
        ],
    }


@click.command()
@click.option("-i", "--input", "input_file", type=click.Path(exists=True), default=None,
              help="Input markdown file (default: stdin)")
@click.option("-o", "--output", "output_file", type=click.Path(), default=None,
              help="Output JSON file (default: stdout)")
def tasks(input_file: str | None, output_file: str | None) -> None:
    """Parse a markdown plan into task JSON."""
    if input_file:
        text = Path(input_file).read_text()
    else:
        text = sys.stdin.read()

    plan = parse_plan(text)
    try:
        validate_plan(plan)
    except ValueError as e:
        raise click.ClickException(str(e))

    result = plan_to_tasks_dict(plan)
    output = json.dumps(result, indent=2)

    if output_file:
        Path(output_file).write_text(output)
    else:
        click.echo(output)
```

- [ ] **Step 4: Update `tests/test_plan_to_tasks.py` imports**

Change line 4 from:
```python
from scripts.plan_to_tasks import parse_plan, validate_plan, plan_to_tasks_dict
```
to:
```python
from shipyard.commands.tasks import parse_plan, validate_plan, plan_to_tasks_dict
```

- [ ] **Step 5: Run all tasks-related tests**

```bash
pytest tests/test_plan_to_tasks.py tests/test_commands_tasks.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 6: Commit**

```bash
git add shipyard/commands/tasks.py tests/test_commands_tasks.py tests/test_plan_to_tasks.py
git commit -m "feat: add shipyard tasks command"
```

---

### Task 3: `shipyard sync` command

**Depends on:** Task 1

**Files:**
- Create: `shipyard/commands/sync.py`
- Modify: `tests/test_sync_to_github.py`
- Create: `tests/test_commands_sync.py`

- [ ] **Step 1: Write the failing CliRunner tests**

Create `tests/test_commands_sync.py`:

```python
import json

from click.testing import CliRunner

from shipyard.commands.sync import sync


def test_sync_dry_run_reads_stdin():
    runner = CliRunner()
    data = {
        "title": "My Epic",
        "body": "Goal.",
        "tasks": [{"id": "1", "subject": "Task A", "description": "Do A.", "status": "pending", "dependencies": []}],
    }
    result = runner.invoke(sync, ["--dry-run"], input=json.dumps(data))
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_sync_exits_nonzero_on_invalid_json():
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input='{"title": "x"}')
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_sync.py -v
```

Expected: both tests fail with `ImportError`.

- [ ] **Step 3: Create `shipyard/commands/sync.py`**

Copy all logic functions from `scripts/sync_to_github.py` verbatim (read that file), then make these specific changes:

1. Add `import click` to imports (remove `import argparse` and `import sys` from top-level — `sys` can stay as a local import in the command).
2. Rename the internal `sync(data, repo, dry_run)` function to `run_sync(data, repo, dry_run)` to avoid shadowing the click command. Update the one call site inside `main()` accordingly (which becomes the click command below).
3. Replace `main()` with this click command:

```python
@click.command()
@click.option("-i", "--input", "input_file", type=click.Path(exists=True), default=None,
              help="Input tasks.json (default: stdin)")
@click.option("--repo", default=None, help="Target repo as owner/repo (default: auto-detect)")
@click.option("--dry-run", is_flag=True, help="Print actions without making API calls")
def sync(input_file: str | None, repo: str | None, dry_run: bool) -> None:
    """Sync task JSON to GitHub Issues."""
    import sys
    if input_file:
        data = json.loads(Path(input_file).read_text())
    else:
        data = json.loads(sys.stdin.read())

    try:
        validate(data)
    except ValueError as e:
        raise click.ClickException(str(e))

    resolved_repo = resolve_repo(repo, dry_run)
    exit_code = run_sync(data, resolved_repo, dry_run)
    if exit_code != 0:
        raise SystemExit(exit_code)
```

The full file starts with:
```python
#!/usr/bin/env python3
"""shipyard sync — mirror task JSON to GitHub Issues."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import click
```

- [ ] **Step 4: Update `tests/test_sync_to_github.py`**

Change imports and patches. The full updated file:

```python
import pytest
from unittest.mock import patch
from shipyard.commands.sync import (
    gh,
    create_issue,
    add_blocked_by,
    task_body,
)


@patch("shipyard.commands.sync.subprocess")
def test_gh_runs_command(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "output\n"
    result = gh(["issue", "list"])
    assert result == "output"
    mock_subprocess.run.assert_called_once()


@patch("shipyard.commands.sync.subprocess")
def test_gh_raises_on_nonzero(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "error msg"
    mock_subprocess.run.return_value.stdout = ""
    with pytest.raises(RuntimeError, match="gh command failed"):
        gh(["issue", "create", "--title", "x"])


@patch("shipyard.commands.sync.subprocess")
def test_create_issue_parses_number_from_url(mock_subprocess):
    mock_subprocess.run.side_effect = [
        type("R", (), {"returncode": 0, "stdout": "https://github.com/owner/repo/issues/42\n", "stderr": ""})(),
        type("R", (), {"returncode": 0, "stdout": "123456\n", "stderr": ""})(),
    ]
    ref = create_issue("owner/repo", "My Title", "My Body", dry_run=False)
    assert ref.number == 42
    assert ref.database_id == 123456
    assert ref.url == "https://github.com/owner/repo/issues/42"


@patch("shipyard.commands.sync.subprocess")
def test_create_issue_dry_run_makes_no_subprocess_calls(mock_subprocess):
    ref = create_issue("owner/repo", "Title", "Body", dry_run=True)
    mock_subprocess.run.assert_not_called()
    assert ref.number == 0


@patch("shipyard.commands.sync.subprocess")
def test_add_blocked_by_404_is_soft_failure(mock_subprocess, capsys):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "404 Not Found"
    mock_subprocess.run.return_value.stdout = ""
    add_blocked_by("owner/repo", 5, 500, 3, 300, dry_run=False)
    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "dependencies API" in captured.out


def test_task_body_pending():
    task = {"description": "Do X", "status": "pending", "dependencies": []}
    body = task_body(task)
    assert "⬜" in body
    assert "Do X" in body


def test_task_body_with_deps():
    task = {"description": "Do Y", "status": "pending", "dependencies": ["1", "3"]}
    body = task_body(task)
    assert "1, 3" in body
```

- [ ] **Step 5: Run all sync-related tests**

```bash
pytest tests/test_sync_to_github.py tests/test_commands_sync.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 6: Commit**

```bash
git add shipyard/commands/sync.py tests/test_commands_sync.py tests/test_sync_to_github.py
git commit -m "feat: add shipyard sync command"
```

---

### Task 4: `shipyard find-work` command

**Depends on:** Task 1

**Files:**
- Create: `shipyard/commands/find_work.py`
- Modify: `tests/test_find_epic_work.py`
- Create: `tests/test_commands_find_work.py`

- [ ] **Step 1: Write the failing CliRunner test**

Create `tests/test_commands_find_work.py`:

```python
from unittest.mock import patch
from click.testing import CliRunner
from shipyard.commands.find_work import find_work


def test_find_work_errors_without_github_repository(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("EVENT_NAME", raising=False)
    runner = CliRunner()
    result = runner.invoke(find_work)
    assert result.exit_code != 0


@patch("shipyard.commands.find_work.gh_get")
@patch("shipyard.commands.find_work.set_output")
def test_find_work_no_unblocked_sets_has_work_false(mock_set_output, mock_gh_get, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("ISSUE_NUMBER", "10")
    monkeypatch.delenv("PR_BODY", raising=False)
    # Epic issue
    mock_gh_get.side_effect = [
        {"number": 10, "title": "My Epic", "body": ""},   # epic fetch
        [],                                                  # sub_issues (empty)
    ]
    runner = CliRunner()
    result = runner.invoke(find_work)
    assert result.exit_code == 0
    mock_set_output.assert_called_with("has_work", "false")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_find_work.py -v
```

Expected: both tests fail with `ImportError`.

- [ ] **Step 3: Create `shipyard/commands/find_work.py`**

Copy all logic functions from `scripts/find_epic_work.py` verbatim (read that file), then:

1. Add `import click` to imports. Remove the unused `from pathlib import Path` import.
2. Replace `main()` with this click command:

```python
@click.command("find-work")
def find_work() -> None:
    """Find unblocked sub-issues for the current epic (CI use only)."""
    import sys
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
    work = build_work_json(epic, unblocked, repo)
    set_output("has_work", "true")
    set_output("work_json", json.dumps(work))
```

The file header:
```python
#!/usr/bin/env python3
"""shipyard find-work — find unblocked sub-issues for the current epic (CI use only)."""

import json
import os
import re
import subprocess

import click
```

- [ ] **Step 4: Update `tests/test_find_epic_work.py`**

Change all imports and patches. Full updated file:

```python
from unittest.mock import patch
from shipyard.commands.find_work import (
    parse_closing_references,
    find_unblocked_sub_issues,
    build_work_json,
    set_output,
    resolve_epic_number,
)


def test_parse_closing_references_standard():
    body = "Closes #42\nFixes #7\nResolves #100"
    assert parse_closing_references(body) == [42, 7, 100]


def test_parse_closing_references_empty():
    assert parse_closing_references("No references here") == []


def test_parse_closing_references_case_insensitive():
    assert parse_closing_references("CLOSES #5") == [5]


@patch("shipyard.commands.find_work.gh_get")
def test_find_unblocked_filters_open_blockers(mock_get):
    def side_effect(path):
        if "sub_issues" in path:
            return [
                {"number": 2, "state": "open", "title": "Task A", "body": ""},
                {"number": 3, "state": "open", "title": "Task B", "body": ""},
                {"number": 4, "state": "closed", "title": "Task C", "body": ""},
            ]
        if "2/dependencies" in path:
            return [{"state": "open", "number": 1}]
        if "3/dependencies" in path:
            return []
        return []
    mock_get.side_effect = side_effect
    result = find_unblocked_sub_issues(10, "owner/repo")
    assert len(result) == 1
    assert result[0]["number"] == 3


def test_build_work_json_structure():
    epic = {"number": 10, "title": "My Epic", "body": "Do stuff"}
    issues = [{"number": 5, "title": "Task A", "body": "Spec A"}]
    result = build_work_json(epic, issues, "owner/repo")
    assert result["epic_number"] == 10
    assert result["repo"] == "owner/repo"
    assert len(result["issues"]) == 1
    assert result["issues"][0]["number"] == 5


def test_set_output_to_stdout_when_no_github_output(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    set_output("has_work", "true")
    captured = capsys.readouterr()
    assert "has_work" in captured.out


@patch("shipyard.commands.find_work.gh_graphql")
def test_resolve_epic_pr_event_graphql_path(mock_gql, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    mock_gql.return_value = {
        "repository": {
            "issue": {
                "parent": {
                    "number": 10,
                    "labels": {"nodes": [{"name": "in-progress"}]},
                }
            }
        }
    }
    result = resolve_epic_number("pull_request", None, "Closes #5", "owner", "repo")
    assert result == 10


def test_resolve_epic_issues_event():
    result = resolve_epic_number("issues", 7, "", "owner", "repo")
    assert result == 7


def test_resolve_epic_workflow_dispatch():
    result = resolve_epic_number("workflow_dispatch", 15, "", "owner", "repo")
    assert result == 15
```

- [ ] **Step 5: Run all find-work-related tests**

```bash
pytest tests/test_find_epic_work.py tests/test_commands_find_work.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 6: Commit**

```bash
git add shipyard/commands/find_work.py tests/test_commands_find_work.py tests/test_find_epic_work.py
git commit -m "feat: add shipyard find-work command"
```

---

### Task 5: `shipyard execute` command

**Depends on:** Task 1

**Files:**
- Create: `shipyard/prompts/` (move from `prompts/`)
- Create: `shipyard/commands/execute.py`
- Modify: `tests/test_executor.py`

- [ ] **Step 1: Move the prompts directory into the package**

```bash
cp -r prompts/ shipyard/prompts/
```

Verify the four files exist:
```bash
ls shipyard/prompts/
# implementer.md  spec-reviewer.md  code-quality-reviewer.md  planner.md
```

- [ ] **Step 2: Create `shipyard/commands/execute.py`**

Copy all content from `scripts/executor.py` verbatim (read that file), then make these specific changes:

**Change 1** — update the module docstring and remove argparse, add click:

Replace the imports block at the top with:
```python
#!/usr/bin/env python3
"""shipyard execute — run the three-agent pipeline for unblocked issues (CI use only)."""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import click
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk import AssistantMessage, TextBlock
```

**Change 2** — update `PROMPTS_DIR` to point inside the package. Replace:
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```
with:
```python
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
```
(`__file__` is now `shipyard/commands/execute.py`, so `parent.parent` = `shipyard/`, and `shipyard/prompts/` is correct.)

**Change 3** — replace `main()` with a click command at the bottom of the file:

```python
@click.command()
def execute() -> None:
    """Run the three-agent pipeline for unblocked issues (CI use only)."""
    work_json_str = os.environ.get("WORK_JSON")
    if not work_json_str:
        raise click.ClickException("$WORK_JSON is not set.")

    data = json.loads(work_json_str)
    work = WorkSpec(
        epic_number=data["epic_number"],
        epic_title=data["epic_title"],
        epic_body=data.get("epic_body", ""),
        repo=data["repo"],
        issues=[IssueWork(**i) for i in data["issues"]],
    )

    run_id = os.environ.get("GITHUB_RUN_ID") or str(int(time.time()))
    branch = f"shipyard/epic-{work.epic_number}-run-{run_id}"
    git_create_and_checkout_branch(branch)
    print(f"Branch: {branch}")

    results = asyncio.run(run_all_issues(work))

    successful = [n for n, ok in results.items() if ok]
    failed = [n for n, ok in results.items() if not ok]

    print(f"\n── Results: {len(successful)} succeeded, {len(failed)} failed")

    if not successful:
        print("No issues implemented — skipping PR creation.")
        raise SystemExit(1)

    git_push_branch(branch)
    pr_title = f"shipyard: implement {len(successful)} issue(s) from epic #{work.epic_number}"
    pr_body = close_issues_body(successful)
    pr_url = create_pull_request(work.repo, branch, pr_title, pr_body)
    print(f"\nPR created: {pr_url}")

    if failed:
        print(f"WARNING: {len(failed)} issue(s) failed: {failed}")
        raise SystemExit(1)
```

- [ ] **Step 3: Update `tests/test_executor.py`**

Change all imports and patch paths. Full updated file:

```python
import pytest
from unittest.mock import AsyncMock, patch
from shipyard.commands.execute import (
    parse_implementer_status,
    parse_review_verdict,
    format_prompt,
    IssueWork,
    WorkSpec,
    ImplementerStatus,
    close_issues_body,
)


def test_parse_status_done():
    assert parse_implementer_status("some text\nStatus: DONE\nmore") == ImplementerStatus.DONE


def test_parse_status_done_with_concerns():
    assert parse_implementer_status("DONE_WITH_CONCERNS") == ImplementerStatus.DONE_WITH_CONCERNS


def test_parse_status_blocked():
    assert parse_implementer_status("BLOCKED\ncan't find module") == ImplementerStatus.BLOCKED


def test_parse_status_needs_context():
    assert parse_implementer_status("NEEDS_CONTEXT: what branch?") == ImplementerStatus.NEEDS_CONTEXT


def test_parse_status_defaults_to_blocked_on_no_match():
    assert parse_implementer_status("no status here at all") == ImplementerStatus.BLOCKED


def test_parse_review_verdict_approved():
    assert parse_review_verdict("APPROVED\nGreat work") is True


def test_parse_review_verdict_changes_requested():
    assert parse_review_verdict("CHANGES_REQUESTED\nMissing test") is False


def test_parse_review_verdict_defaults_false():
    assert parse_review_verdict("ambiguous output") is False


def test_format_prompt_substitutes_placeholders():
    template = "Task: {TASK_DESCRIPTION}\nBase: {BASE_SHA}"
    result = format_prompt(template, TASK_DESCRIPTION="Do X", BASE_SHA="abc123")
    assert result == "Task: Do X\nBase: abc123"


def test_close_issues_body():
    body = close_issues_body([5, 12, 99])
    assert "Closes #5" in body
    assert "Closes #12" in body
    assert "Closes #99" in body


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
@patch("shipyard.commands.execute.create_pull_request", return_value="https://github.com/o/r/pull/9")
async def test_pipeline_happy_path(mock_pr, mock_comment, mock_reset, mock_agent):
    mock_agent.side_effect = [
        "Status: DONE\nFiles: foo.py",
        "APPROVED",
        "APPROVED",
    ]
    from shipyard.commands.execute import run_issue_pipeline
    issue = IssueWork(number=5, title="Do X", body="spec")
    work = WorkSpec(
        epic_number=10, epic_title="Epic", epic_body="",
        repo="owner/repo", issues=[issue]
    )
    result = await run_issue_pipeline(issue, work, base_sha="start123")
    assert result is True
    mock_reset.assert_not_called()
    mock_pr.assert_not_called()


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_blocked_resets_and_comments(mock_comment, mock_reset, mock_agent):
    mock_agent.return_value = "BLOCKED\nCannot find module X"
    from shipyard.commands.execute import run_issue_pipeline
    issue = IssueWork(number=5, title="Do X", body="spec")
    work = WorkSpec(
        epic_number=10, epic_title="Epic", epic_body="",
        repo="owner/repo", issues=[issue]
    )
    result = await run_issue_pipeline(issue, work, base_sha="start123")
    assert result is False
    mock_reset.assert_called_once_with("start123")
    mock_comment.assert_called_once()
    comment_body = mock_comment.call_args[0][2]
    assert "BLOCKED" in comment_body


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_spec_failure_triggers_retry(mock_comment, mock_reset, mock_agent):
    mock_agent.side_effect = [
        "Status: DONE\nFiles: foo.py",
        "CHANGES_REQUESTED\nMissing test",
        "Status: DONE\nFiles: foo.py",
        "APPROVED",
        "APPROVED",
    ]
    from shipyard.commands.execute import run_issue_pipeline
    issue = IssueWork(number=5, title="Do X", body="spec")
    work = WorkSpec(
        epic_number=10, epic_title="Epic", epic_body="",
        repo="owner/repo", issues=[issue]
    )
    result = await run_issue_pipeline(issue, work, base_sha="start123")
    assert result is True
    assert mock_agent.call_count == 5
```

- [ ] **Step 4: Run all execute-related tests**

```bash
pytest tests/test_executor.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shipyard/prompts/ shipyard/commands/execute.py tests/test_executor.py
git commit -m "feat: add shipyard execute command, move prompts into package"
```

---

### Task 6: `shipyard init` command and workflow template

**Depends on:** Task 1

**Files:**
- Create: `shipyard/templates/epic-driver.yml`
- Create: `shipyard/commands/init.py`
- Create: `tests/test_commands_init.py`
- Modify: `tests/test_workflow.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_commands_init.py`:

```python
import yaml
from pathlib import Path
from click.testing import CliRunner
from shipyard.commands.init import init


def test_init_creates_workflow_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    assert workflow.exists()


def test_init_fails_if_file_already_exists(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code != 0
    assert workflow.read_text() == "existing content"


def test_init_force_overwrites_existing_file(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path), "--force"])
    assert result.exit_code == 0
    assert workflow.read_text() != "existing content"


def test_init_template_is_valid_yaml(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    data = yaml.safe_load(workflow.read_text())
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_init_template_has_required_content(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content
    assert "@anthropic-ai/claude-code" in content
    assert "shipyard find-work" in content
    assert "shipyard execute" in content


def test_init_defaults_to_current_directory():
    runner = CliRunner()
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(init, catch_exceptions=False, args=[], env={}, obj=None,
                               standalone_mode=True)
    # Just verify no crash when PATH argument is absent — actual path test above
```

Replace the last test with a simpler version:

```python
def test_init_pins_version_in_workflow(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    # Version placeholder should be replaced (not literally present)
    assert "SHIPYARD_VERSION" not in content
    assert "shipyard==" in content
```

So the full `tests/test_commands_init.py`:

```python
import yaml
from pathlib import Path
from click.testing import CliRunner
from shipyard.commands.init import init


def test_init_creates_workflow_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    assert workflow.exists()


def test_init_fails_if_file_already_exists(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code != 0
    assert workflow.read_text() == "existing content"


def test_init_force_overwrites_existing_file(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path), "--force"])
    assert result.exit_code == 0
    assert workflow.read_text() != "existing content"


def test_init_template_is_valid_yaml(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    data = yaml.safe_load(workflow.read_text())
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_init_template_has_required_content(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content
    assert "@anthropic-ai/claude-code" in content
    assert "shipyard find-work" in content
    assert "shipyard execute" in content


def test_init_pins_version_in_workflow(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    assert "SHIPYARD_VERSION" not in content
    assert "shipyard==" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_commands_init.py -v
```

Expected: all 6 tests fail with `ImportError`.

- [ ] **Step 3: Create `shipyard/templates/epic-driver.yml`**

```yaml
name: Epic Driver

on:
  issues:
    types: [labeled]
  pull_request:
    types: [closed]
  workflow_dispatch:
    inputs:
      issue_number:
        description: "Epic issue number to drive"
        required: true
        type: string

jobs:
  find-work:
    name: Find unblocked issues
    if: |
      (github.event_name == 'issues' &&
       github.event.label.name == 'in-progress' &&
       github.event.issue.pull_request == '') ||
      (github.event_name == 'pull_request' &&
       github.event.pull_request.merged == true) ||
      github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
      pull-requests: read
    outputs:
      has_work: ${{ steps.find-work.outputs.has_work }}
      work_json: ${{ steps.find-work.outputs.work_json }}

    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install shipyard
        run: pip install shipyard==SHIPYARD_VERSION

      - name: Find epic and unblocked issues
        id: find-work
        env:
          GH_TOKEN: ${{ github.token }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          EVENT_NAME: ${{ github.event_name }}
          ISSUE_NUMBER: ${{ github.event.issue.number || inputs.issue_number || '' }}
          PR_BODY: ${{ github.event.pull_request.body || '' }}
        run: shipyard find-work

  execute:
    name: Execute tasks with Agent SDK
    needs: find-work
    if: needs.find-work.outputs.has_work == 'true'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Configure git identity
        run: |
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git config user.name "github-actions[bot]"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install Claude Code CLI
        run: npm install -g @anthropic-ai/claude-code

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install shipyard
        run: pip install shipyard==SHIPYARD_VERSION

      - name: Run executor
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          GH_TOKEN: ${{ github.token }}
          WORK_JSON: ${{ needs.find-work.outputs.work_json }}
          GITHUB_RUN_ID: ${{ github.run_id }}
        run: shipyard execute
```

- [ ] **Step 4: Create `shipyard/commands/init.py`**

```python
"""shipyard init — set up the Shipyard workflow in a repository."""

import importlib.metadata
from pathlib import Path

import click


@click.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing workflow file")
def init(path: str, force: bool) -> None:
    """Set up the Shipyard epic-driver workflow in a repository.

    PATH defaults to the current directory.
    """
    dest = Path(path) / ".github" / "workflows" / "epic-driver.yml"

    if dest.exists() and not force:
        raise click.ClickException(
            f"{dest} already exists. Use --force to overwrite."
        )

    try:
        version = importlib.metadata.version("shipyard")
    except importlib.metadata.PackageNotFoundError:
        version = "0.1.0"

    template_path = Path(__file__).parent.parent / "templates" / "epic-driver.yml"
    content = template_path.read_text().replace("SHIPYARD_VERSION", version)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)

    click.echo(f"Created {dest}")
    click.echo(
        "Next step: add CLAUDE_CODE_OAUTH_TOKEN as a secret in your GitHub repository settings."
    )
```

- [ ] **Step 5: Update `tests/test_workflow.py` to also test the bundled template**

Replace the file with:

```python
import yaml
from pathlib import Path


# ── Dogfood workflow (this repo's own .github/workflows/epic-driver.yml) ──

def test_epic_driver_workflow_valid_yaml():
    path = Path(".github/workflows/epic-driver.yml")
    assert path.exists(), "Workflow file missing"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_execute_job_has_claude_oauth_token():
    path = Path(".github/workflows/epic-driver.yml")
    content = path.read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content


def test_execute_job_installs_claude_code_cli():
    path = Path(".github/workflows/epic-driver.yml")
    content = path.read_text()
    assert "@anthropic-ai/claude-code" in content


# ── Bundled template (shipped inside the package) ──

def test_template_workflow_valid_yaml():
    path = Path("shipyard/templates/epic-driver.yml")
    assert path.exists(), "Bundled template missing"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_template_has_claude_oauth_token():
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content


def test_template_installs_claude_code_cli():
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "@anthropic-ai/claude-code" in content


def test_template_uses_shipyard_cli_commands():
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "shipyard find-work" in content
    assert "shipyard execute" in content


def test_template_has_version_placeholder_replaced_by_init(tmp_path):
    """Verify the raw template still has the SHIPYARD_VERSION placeholder
    (init replaces it at copy time)."""
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "SHIPYARD_VERSION" in content
```

- [ ] **Step 6: Run all init and workflow tests**

```bash
pytest tests/test_commands_init.py tests/test_workflow.py -v
```

Expected: all 14 tests pass.

- [ ] **Step 7: Commit**

```bash
git add shipyard/templates/ shipyard/commands/init.py tests/test_commands_init.py tests/test_workflow.py
git commit -m "feat: add shipyard init command and bundled workflow template"
```

---

### Task 7: CLI entry point

**Depends on:** Tasks 2, 3, 4, 5, 6

**Files:**
- Create: `shipyard/cli.py`
- Modify: `tests/test_scaffolding.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scaffolding.py`:

```python
from click.testing import CliRunner


def test_cli_entry_point_lists_all_commands():
    from shipyard.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "tasks" in result.output
    assert "sync" in result.output
    assert "init" in result.output
    assert "find-work" in result.output
    assert "execute" in result.output
```

The full updated `tests/test_scaffolding.py`:

```python
import importlib
from pathlib import Path

from click.testing import CliRunner


def test_shipyard_package_importable():
    mod = importlib.import_module("shipyard")
    assert mod is not None


def test_shipyard_commands_package_importable():
    mod = importlib.import_module("shipyard.commands")
    assert mod is not None


def test_required_files_exist():
    root = Path(__file__).parent.parent
    assert (root / "pyproject.toml").exists()
    assert (root / "requirements.txt").exists()
    assert (root / "tests" / "fixtures").is_dir()


def test_cli_entry_point_lists_all_commands():
    from shipyard.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "tasks" in result.output
    assert "sync" in result.output
    assert "init" in result.output
    assert "find-work" in result.output
    assert "execute" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scaffolding.py::test_cli_entry_point_lists_all_commands -v
```

Expected: fails with `ImportError` (`shipyard.cli` not found).

- [ ] **Step 3: Create `shipyard/cli.py`**

```python
"""Shipyard CLI entry point."""

import click

from shipyard.commands.execute import execute
from shipyard.commands.find_work import find_work
from shipyard.commands.init import init
from shipyard.commands.sync import sync
from shipyard.commands.tasks import tasks


@click.group()
def main() -> None:
    """Shipyard — agentic GitHub Actions pipeline."""


main.add_command(init)
main.add_command(tasks)
main.add_command(sync)
main.add_command(find_work, name="find-work")
main.add_command(execute)
```

- [ ] **Step 4: Run all scaffolding tests**

```bash
pytest tests/test_scaffolding.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Verify the installed CLI works**

```bash
shipyard --help
```

Expected output includes: `tasks`, `sync`, `init`, `find-work`, `execute`.

```bash
shipyard tasks --help
shipyard sync --help
shipyard init --help
```

Expected: each shows usage with the correct options.

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (42 original + new ones from Tasks 2–6).

- [ ] **Step 7: Commit**

```bash
git add shipyard/cli.py tests/test_scaffolding.py
git commit -m "feat: wire shipyard CLI entry point"
```

---

### Task 8: Delete `scripts/`, update dogfood workflow

**Depends on:** Task 7

**Files:**
- Delete: `scripts/`
- Modify: `.github/workflows/epic-driver.yml`

- [ ] **Step 1: Verify all tests pass before deleting anything**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Delete the `scripts/` directory**

```bash
rm -rf scripts/
```

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
pytest tests/ -v
```

Expected: all tests still pass (no imports from `scripts.*` remain in test files after Tasks 2–5).

- [ ] **Step 4: Update the dogfood workflow**

Replace `.github/workflows/epic-driver.yml` with:

```yaml
name: Epic Driver

on:
  issues:
    types: [labeled]
  pull_request:
    types: [closed]
  workflow_dispatch:
    inputs:
      issue_number:
        description: "Epic issue number to drive"
        required: true
        type: string

jobs:
  find-work:
    name: Find unblocked issues
    if: |
      (github.event_name == 'issues' &&
       github.event.label.name == 'in-progress' &&
       github.event.issue.pull_request == '') ||
      (github.event_name == 'pull_request' &&
       github.event.pull_request.merged == true) ||
      github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
      pull-requests: read
    outputs:
      has_work: ${{ steps.find-work.outputs.has_work }}
      work_json: ${{ steps.find-work.outputs.work_json }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install shipyard (editable)
        run: pip install -e ".[dev]"

      - name: Find epic and unblocked issues
        id: find-work
        env:
          GH_TOKEN: ${{ github.token }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          EVENT_NAME: ${{ github.event_name }}
          ISSUE_NUMBER: ${{ github.event.issue.number || inputs.issue_number || '' }}
          PR_BODY: ${{ github.event.pull_request.body || '' }}
        run: shipyard find-work

  execute:
    name: Execute tasks with Agent SDK
    needs: find-work
    if: needs.find-work.outputs.has_work == 'true'
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Configure git identity
        run: |
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git config user.name "github-actions[bot]"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install Claude Code CLI
        run: npm install -g @anthropic-ai/claude-code

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install shipyard (editable)
        run: pip install -e ".[dev]"

      - name: Run executor
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          GH_TOKEN: ${{ github.token }}
          WORK_JSON: ${{ needs.find-work.outputs.work_json }}
          GITHUB_RUN_ID: ${{ github.run_id }}
        run: shipyard execute
```

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass, including `test_workflow.py` (dogfood workflow still has `CLAUDE_CODE_OAUTH_TOKEN`, `@anthropic-ai/claude-code`, and correct job structure).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: delete scripts/, update dogfood workflow to use shipyard CLI"
```
