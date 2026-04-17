import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from shipyard.commands.sync import (
    add_blocked_by,
    add_sub_issue,
    create_issue,
    ensure_label_exists,
    gh,
    resolve_repo,
    run_sync,
    task_body,
    validate,
)
from shipyard.schemas import Subtask, SubtaskList

# ---------------------------------------------------------------------------
# gh helper
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess")
def test_gh_runs_command(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "output\n"
    result = gh(["issue", "list"])
    assert result == "output"
    mock_subprocess.run.assert_called_once()


@patch("shipyard.utils.gh.subprocess")
def test_gh_raises_on_nonzero(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "error msg"
    mock_subprocess.run.return_value.stdout = ""
    with pytest.raises(RuntimeError, match="gh command failed"):
        gh(["issue", "create", "--title", "x"])


def test_gh_dry_run_prints_and_returns_empty(capsys):
    result = gh(["issue", "list"], dry_run=True)
    assert result == ""
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "issue list" in out


def test_gh_dry_run_includes_label(capsys):
    gh(["issue", "list"], dry_run=True, dry_label="my label")
    out = capsys.readouterr().out
    assert "my label" in out


# ---------------------------------------------------------------------------
# resolve_repo
# ---------------------------------------------------------------------------


def test_resolve_repo_uses_flag():
    assert resolve_repo("myorg/myrepo", dry_run=False) == "myorg/myrepo"


@patch("shipyard.utils.gh.gh", return_value="owner/detected")
def test_resolve_repo_auto_detects(mock_gh):
    assert resolve_repo(None, dry_run=False) == "owner/detected"


def test_resolve_repo_dry_run_placeholder():
    result = resolve_repo(None, dry_run=True)
    assert result == "<owner>/<repo>"


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess")
def test_create_issue_parses_number_from_url(mock_subprocess):
    mock_subprocess.run.side_effect = [
        type(
            "R",
            (),
            {"returncode": 0, "stdout": "https://github.com/owner/repo/issues/42\n", "stderr": ""},
        )(),
        type("R", (), {"returncode": 0, "stdout": "123456\n", "stderr": ""})(),
    ]
    ref = create_issue("owner/repo", "My Title", "My Body", dry_run=False)
    assert ref.number == 42
    assert ref.database_id == 123456
    assert ref.url == "https://github.com/owner/repo/issues/42"


@patch("shipyard.utils.gh.subprocess")
def test_create_issue_dry_run_makes_no_subprocess_calls(mock_subprocess):
    ref = create_issue("owner/repo", "Title", "Body", dry_run=True)
    mock_subprocess.run.assert_not_called()
    assert ref.number == 0


@patch("shipyard.utils.gh.subprocess")
def test_create_issue_raises_on_bad_url(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "not-a-url\n"
    mock_subprocess.run.return_value.stderr = ""
    with pytest.raises(RuntimeError, match="Unexpected gh issue create output"):
        create_issue("owner/repo", "T", "B", dry_run=False)


# ---------------------------------------------------------------------------
# add_sub_issue
# ---------------------------------------------------------------------------


def test_add_sub_issue_dry_run_prints(capsys):
    add_sub_issue("owner/repo", 1, 999, 5, dry_run=True)
    out = capsys.readouterr().out
    assert "dry-run" in out


# ---------------------------------------------------------------------------
# add_blocked_by
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess")
def test_add_blocked_by_404_is_soft_failure(mock_subprocess, capsys):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "404 Not Found"
    mock_subprocess.run.return_value.stdout = ""
    add_blocked_by("owner/repo", 5, 500, 3, 300, dry_run=False)
    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "dependencies API" in captured.out


@patch("shipyard.utils.gh.subprocess")
def test_add_blocked_by_reraises_non_404(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "500 Internal Server Error"
    mock_subprocess.run.return_value.stdout = ""
    with pytest.raises(RuntimeError):
        add_blocked_by("owner/repo", 5, 500, 3, 300, dry_run=False)


def test_add_blocked_by_dry_run(capsys):
    add_blocked_by("owner/repo", 5, 500, 3, 300, dry_run=True)
    out = capsys.readouterr().out
    assert "dry-run" in out


# ---------------------------------------------------------------------------
# ensure_label_exists
# ---------------------------------------------------------------------------


@patch("shipyard.commands.sync.gh")
def test_ensure_label_exists_skips_create_if_present(mock_gh):
    mock_gh.return_value = "in-progress\nbug"
    ensure_label_exists("owner/repo", "in-progress", "0075ca", "desc")
    # Only one call (the list) — no create call
    assert mock_gh.call_count == 1


@patch("shipyard.commands.sync.gh")
def test_ensure_label_exists_creates_if_absent(mock_gh):
    mock_gh.return_value = "bug\nenhancement"
    ensure_label_exists("owner/repo", "in-progress", "0075ca", "desc")
    assert mock_gh.call_count == 2
    create_args = mock_gh.call_args_list[1][0][0]
    assert "label" in create_args
    assert "create" in create_args


# ---------------------------------------------------------------------------
# task_body
# ---------------------------------------------------------------------------


def test_task_body_pending():
    subtask = Subtask(task_id="1", title="X", description="Do X", status="pending")
    body = task_body(subtask)
    assert "⬜" in body
    assert "Do X" in body


def test_task_body_in_progress():
    subtask = Subtask(task_id="1", title="X", description="Doing Y", status="in_progress")
    assert "🔄" in task_body(subtask)


def test_task_body_completed():
    subtask = Subtask(task_id="1", title="X", description="Done Z", status="completed")
    assert "✅" in task_body(subtask)


def test_task_body_with_deps():
    subtask = Subtask(
        task_id="2", title="X", description="Do Y", status="pending", blocked_by={"1", "3"}
    )
    body = task_body(subtask)
    assert "1, 3" in body


def test_task_body_no_description():
    subtask = Subtask(task_id="1", title="X", description="", status="pending")
    body = task_body(subtask)
    assert "pending" in body


def test_task_body_unknown_status_defaults_to_pending_emoji():
    subtask = Subtask(task_id="1", title="X", description="X", status="mystery")
    assert "⬜" in task_body(subtask)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _minimal_task_list(**overrides: object) -> SubtaskList:
    defaults: dict = {
        "title": "My Plan",
        "description": "Goal.",
        "tasks": {
            "1": Subtask(task_id="1", title="Task A", description="Do A"),
        },
    }
    defaults.update(overrides)
    return SubtaskList(**defaults)


def test_validate_passes_on_valid_input():
    validate(_minimal_task_list())


def test_validate_raises_on_empty_tasks():
    with pytest.raises(ValueError, match="tasks"):
        validate(_minimal_task_list(tasks={}))


def test_validate_raises_on_unknown_dependency():
    tasks = {
        "1": Subtask(task_id="1", title="A", description="Do A", blocked_by={"99"}),
    }
    with pytest.raises(ValueError, match="unknown dependency"):
        validate(_minimal_task_list(tasks=tasks))


# ---------------------------------------------------------------------------
# run_sync — dry-run integration
# ---------------------------------------------------------------------------


def _minimal_plan(*, with_deps: bool = False) -> SubtaskList:
    tasks = {
        "1": Subtask(task_id="1", title="Task A", description="Do A."),
    }
    if with_deps:
        tasks["2"] = Subtask(task_id="2", title="Task B", description="Do B.", blocked_by={"1"})
    return SubtaskList(title="My Plan", description="Goal.", tasks=tasks)


def test_run_sync_dry_run_succeeds(capsys):
    code = run_sync(_minimal_plan(), "owner/repo", dry_run=True)
    assert code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out


def test_run_sync_dry_run_with_dependencies(capsys):
    code = run_sync(_minimal_plan(with_deps=True), "owner/repo", dry_run=True)
    assert code == 0
    out = capsys.readouterr().out
    assert "blocked" in out.lower() or "blocked-by" in out.lower()


@patch("shipyard.commands.sync.create_issue", side_effect=RuntimeError("API down"))
def test_run_sync_parent_creation_failure_returns_1(mock_create, capsys):
    code = run_sync(_minimal_plan(), "owner/repo", dry_run=False)
    assert code == 1


# ---------------------------------------------------------------------------
# sync CLI command
# ---------------------------------------------------------------------------


def _minimal_plan_json(*, with_deps: bool = False) -> str:
    tasks = {
        "1": {"task_id": "1", "title": "Task A", "description": "Do A.", "blocked_by": []},
    }
    if with_deps:
        tasks["2"] = {
            "task_id": "2",
            "title": "Task B",
            "description": "Do B.",
            "blocked_by": ["1"],
        }
    return json.dumps({"title": "My Plan", "description": "Goal.", "tasks": tasks})


def test_sync_cli_dry_run_from_stdin():
    from shipyard.commands.sync import sync

    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run", "--repo", "owner/repo"], input=_minimal_plan_json())
    assert result.exit_code == 0


def test_sync_cli_invalid_json_raises():
    from shipyard.commands.sync import sync

    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input="not json")
    assert result.exit_code != 0


def test_sync_cli_validation_error_shown():
    from shipyard.commands.sync import sync

    data = json.dumps({"title": "T", "description": "D", "tasks": {}})
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input=data)
    assert result.exit_code != 0
    assert "tasks" in result.output


def test_sync_cli_file_input(tmp_path):
    from shipyard.commands.sync import sync

    f = tmp_path / "tasks.json"
    f.write_text(_minimal_plan_json())
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run", "--repo", "owner/repo", "--input", str(f)])
    assert result.exit_code == 0
