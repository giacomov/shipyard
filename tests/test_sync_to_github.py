import json
import pytest
from unittest.mock import patch, call
from scripts.sync_to_github import (
    gh,
    resolve_repo,
    create_issue,
    add_sub_issue,
    add_blocked_by,
    task_body,
    IssueRef,
)


@patch("scripts.sync_to_github.subprocess")
def test_gh_runs_command(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "output\n"
    result = gh(["issue", "list"])
    assert result == "output"
    mock_subprocess.run.assert_called_once()


@patch("scripts.sync_to_github.subprocess")
def test_gh_raises_on_nonzero(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "error msg"
    mock_subprocess.run.return_value.stdout = ""
    with pytest.raises(RuntimeError, match="gh command failed"):
        gh(["issue", "create", "--title", "x"])


@patch("scripts.sync_to_github.subprocess")
def test_create_issue_parses_number_from_url(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = (
        "https://github.com/owner/repo/issues/42\n"
    )
    # Second call for database id
    mock_subprocess.run.side_effect = [
        type("R", (), {"returncode": 0, "stdout": "https://github.com/owner/repo/issues/42\n", "stderr": ""})(),
        type("R", (), {"returncode": 0, "stdout": "123456\n", "stderr": ""})(),
    ]
    ref = create_issue("owner/repo", "My Title", "My Body", dry_run=False)
    assert ref.number == 42
    assert ref.database_id == 123456
    assert ref.url == "https://github.com/owner/repo/issues/42"


@patch("scripts.sync_to_github.subprocess")
def test_create_issue_dry_run_makes_no_subprocess_calls(mock_subprocess):
    ref = create_issue("owner/repo", "Title", "Body", dry_run=True)
    mock_subprocess.run.assert_not_called()
    assert ref.number == 0


@patch("scripts.sync_to_github.subprocess")
def test_add_blocked_by_404_is_soft_failure(mock_subprocess, capsys):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "404 Not Found"
    mock_subprocess.run.return_value.stdout = ""
    # Should not raise
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
