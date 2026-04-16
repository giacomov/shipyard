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
    task = {"description": "Do X", "status": "pending", "dependencies": []}
    body = task_body(task)
    assert "⬜" in body
    assert "Do X" in body


def test_task_body_in_progress():
    task = {"description": "Doing Y", "status": "in_progress", "dependencies": []}
    assert "🔄" in task_body(task)


def test_task_body_completed():
    task = {"description": "Done Z", "status": "completed", "dependencies": []}
    assert "✅" in task_body(task)


def test_task_body_with_deps():
    task = {"description": "Do Y", "status": "pending", "dependencies": ["1", "3"]}
    body = task_body(task)
    assert "1, 3" in body


def test_task_body_no_description():
    task = {"status": "pending", "dependencies": []}
    body = task_body(task)
    assert "pending" in body


def test_task_body_unknown_status_defaults_to_pending_emoji():
    task = {"description": "X", "status": "mystery", "dependencies": []}
    assert "⬜" in task_body(task)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _valid_data(**overrides) -> dict:
    base = {
        "title": "My Plan",
        "tasks": [
            {"id": "1", "subject": "Task A", "description": "Do A", "dependencies": []},
        ],
    }
    base.update(overrides)
    return base


def test_validate_passes_on_valid_input():
    validate(_valid_data())  # should not raise


def test_validate_raises_on_missing_title():
    with pytest.raises(ValueError, match="title"):
        validate({"tasks": [{"id": "1", "subject": "x", "dependencies": []}]})


def test_validate_raises_on_empty_tasks():
    with pytest.raises(ValueError, match="tasks"):
        validate({"title": "T", "tasks": []})


def test_validate_raises_on_task_missing_id():
    with pytest.raises(ValueError, match='"id"'):
        validate({"title": "T", "tasks": [{"subject": "x", "dependencies": []}]})


def test_validate_raises_on_task_missing_subject():
    with pytest.raises(ValueError, match='"subject"'):
        validate({"title": "T", "tasks": [{"id": "1", "dependencies": []}]})


def test_validate_raises_on_unknown_dependency():
    data = {
        "title": "T",
        "tasks": [{"id": "1", "subject": "A", "dependencies": ["99"]}],
    }
    with pytest.raises(ValueError, match="unknown dependency"):
        validate(data)


# ---------------------------------------------------------------------------
# run_sync — dry-run integration
# ---------------------------------------------------------------------------


def _minimal_plan(*, with_deps: bool = False) -> dict:
    tasks = [
        {
            "id": "1",
            "subject": "Task A",
            "description": "Do A.",
            "status": "pending",
            "dependencies": [],
        },
    ]
    if with_deps:
        tasks.append(
            {
                "id": "2",
                "subject": "Task B",
                "description": "Do B.",
                "status": "pending",
                "dependencies": ["1"],
            },
        )
    return {"title": "My Plan", "body": "Goal.", "tasks": tasks}


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


def test_sync_cli_dry_run_from_stdin():
    from shipyard.commands.sync import sync

    data = json.dumps(_minimal_plan())
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run", "--repo", "owner/repo"], input=data)
    assert result.exit_code == 0


def test_sync_cli_invalid_json_raises():
    from shipyard.commands.sync import sync

    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input="not json")
    assert result.exit_code != 0


def test_sync_cli_validation_error_shown():
    from shipyard.commands.sync import sync

    data = json.dumps({"title": "T", "tasks": []})
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input=data)
    assert result.exit_code != 0
    assert "tasks" in result.output


def test_sync_cli_file_input(tmp_path):
    from shipyard.commands.sync import sync

    f = tmp_path / "tasks.json"
    f.write_text(json.dumps(_minimal_plan()))
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run", "--repo", "owner/repo", "--input", str(f)])
    assert result.exit_code == 0
