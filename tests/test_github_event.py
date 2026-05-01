"""Tests for shipyard.utils.github_event."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from shipyard.utils.github_event import (
    _issue_number_from_plan_branch,
    extract_github_event,
    extract_issue_from_pr_review,
    fetch_issue_context,
)

# ---------------------------------------------------------------------------
# fetch_issue_context
# ---------------------------------------------------------------------------


def test_fetch_issue_context() -> None:
    gh_response: dict[str, Any] = {"number": 5, "title": "Fix bug", "body": "Details here"}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(gh_response)

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        context = fetch_issue_context("owner/repo", 5)

    mock_run.assert_called_once()
    assert context == {
        "issue_number": 5,
        "issue_title": "Fix bug",
        "issue_body": "Details here",
        "repo": "owner/repo",
    }


# ---------------------------------------------------------------------------
# extract_issue_from_pr_review
# ---------------------------------------------------------------------------


def test_extract_issue_from_pr_review_found() -> None:
    event_json: dict[str, Any] = {"pull_request": {"body": "Fixes #123"}}

    result = extract_issue_from_pr_review(event_json)

    assert result == 123


def test_extract_issue_from_pr_review_not_found() -> None:
    event_json: dict[str, Any] = {"pull_request": {"body": "No references"}}

    with pytest.raises(ValueError):
        extract_issue_from_pr_review(event_json)


# ---------------------------------------------------------------------------
# extract_github_event CLI — pull_request_review
# ---------------------------------------------------------------------------


def test_extract_github_event_pr_review(
    tmp_path: Path,
) -> None:
    event_json: dict[str, Any] = {
        "review": {"id": 999, "state": "changes_requested", "body": "Please add tests"},
        "pull_request": {"number": 3, "body": "Closes #7", "head": {"ref": "plan/i7"}},
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    issue_mock = MagicMock()
    issue_mock.returncode = 0
    issue_mock.stdout = json.dumps({"number": 7, "title": "Fix the thing", "body": "Details"})

    inline_mock = MagicMock()
    inline_mock.returncode = 0
    inline_mock.stdout = json.dumps(
        [{"path": "README.md", "body": "Add more detail here", "diff_hunk": "@@ -1,3 +1,4 @@"}]
    )

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", side_effect=[inline_mock, issue_mock]):
        with runner.isolated_filesystem() as isolated_dir:
            result = runner.invoke(extract_github_event, env=env_vars)
            prompt_path = Path(isolated_dir) / "prompt.txt"
            review_path = Path(isolated_dir) / "review-feedback.txt"

            assert result.exit_code == 0, result.output
            assert prompt_path.exists(), "prompt.txt was not written"
            assert review_path.exists(), "review-feedback.txt was not written"
            feedback = review_path.read_text()
            assert "Please add tests" in feedback
            assert "Add more detail here" in feedback
            assert "README.md" in feedback

    output_text = github_output_file.read_text()
    assert "has_review" in output_text
    assert "true" in output_text


def test_extract_github_event_pr_review_inline_only(
    tmp_path: Path,
) -> None:
    """Review body is empty but inline comments carry the feedback."""
    event_json: dict[str, Any] = {
        "review": {"id": 42, "state": "changes_requested", "body": ""},
        "pull_request": {"number": 5, "body": "Closes #9", "head": {"ref": "plan/i9"}},
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    issue_mock = MagicMock()
    issue_mock.returncode = 0
    issue_mock.stdout = json.dumps({"number": 9, "title": "Some issue", "body": "Do stuff"})

    inline_mock = MagicMock()
    inline_mock.returncode = 0
    inline_mock.stdout = json.dumps(
        [{"path": "src/foo.py", "body": "Rename this variable", "diff_hunk": "@@ -10,3 +10,4 @@"}]
    )

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", side_effect=[inline_mock, issue_mock]):
        with runner.isolated_filesystem() as isolated_dir:
            result = runner.invoke(extract_github_event, env=env_vars)
            review_path = Path(isolated_dir) / "review-feedback.txt"

            assert result.exit_code == 0, result.output
            feedback = review_path.read_text()
            assert "Rename this variable" in feedback
            assert "src/foo.py" in feedback


# ---------------------------------------------------------------------------
# extract_github_event CLI — unknown event
# ---------------------------------------------------------------------------


def test_extract_github_event_unknown_event(
    tmp_path: Path,
) -> None:
    event_json: dict[str, Any] = {"action": "opened", "sender": {"login": "someone"}}
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(extract_github_event, env=env_vars)

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# _issue_number_from_plan_branch
# ---------------------------------------------------------------------------


def test_issue_number_from_plan_branch_plan_prefix() -> None:
    assert _issue_number_from_plan_branch("plan/i42") == 42


def test_issue_number_from_plan_branch_shipyard_plan_prefix() -> None:
    assert _issue_number_from_plan_branch("shipyard-plan/i7") == 7


# ---------------------------------------------------------------------------
# extract_github_event CLI — missing env vars
# ---------------------------------------------------------------------------


def test_extract_github_event_missing_event_path() -> None:
    runner = CliRunner()
    result = runner.invoke(extract_github_event, env={})
    assert result.exit_code != 0


def test_extract_github_event_missing_repository(tmp_path: Path) -> None:
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"comment": {}}))

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            extract_github_event,
            env={"GITHUB_EVENT_PATH": str(event_file)},
        )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# extract_github_event CLI — issue comment (non-PR)
# ---------------------------------------------------------------------------


def test_extract_github_event_issue_comment(tmp_path: Path) -> None:
    event_json: dict[str, Any] = {
        "comment": {"body": "Some comment"},
        "issue": {"number": 42, "title": "My Issue", "body": "Issue body"},
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
        "COMMENT_BODY": "Some comment",
    }

    runner = CliRunner()
    with runner.isolated_filesystem() as isolated_dir:
        result = runner.invoke(extract_github_event, env=env_vars)
        prompt_path = Path(isolated_dir) / "prompt.txt"

        assert result.exit_code == 0, result.output
        assert prompt_path.exists()
        assert "My Issue" in prompt_path.read_text()

    output_text = github_output_file.read_text()
    assert "has_review" in output_text
    assert "false" in output_text


# ---------------------------------------------------------------------------
# extract_github_event CLI — /ship replan comment on a plan branch PR
# ---------------------------------------------------------------------------


def test_extract_github_event_replan_comment(tmp_path: Path) -> None:
    event_json: dict[str, Any] = {
        "comment": {"body": "/ship replan"},
        "issue": {
            "number": 7,
            "title": "Plan PR",
            "body": "body",
            "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/7"},
        },
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    branch_mock = MagicMock(returncode=0, stdout="plan/i5\n")
    issue_mock = MagicMock(
        returncode=0,
        stdout=json.dumps({"number": 5, "title": "Issue 5", "body": "Details"}),
    )
    comments_mock = MagicMock(returncode=0, stdout="Some review feedback")

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
        "COMMENT_BODY": "/ship replan",
    }

    runner = CliRunner()
    with patch("subprocess.run", side_effect=[branch_mock, issue_mock, comments_mock]):
        with runner.isolated_filesystem() as isolated_dir:
            result = runner.invoke(extract_github_event, env=env_vars)
            prompt_path = Path(isolated_dir) / "prompt.txt"
            review_path = Path(isolated_dir) / "review-feedback.txt"

            assert result.exit_code == 0, result.output
            assert prompt_path.exists()
            assert review_path.exists()
            assert "Issue 5" in prompt_path.read_text()

    output_text = github_output_file.read_text()
    assert "has_review" in output_text
    assert "true" in output_text
    assert "issue_number" in output_text


def test_extract_github_event_replan_wrong_branch(tmp_path: Path) -> None:
    """Replan on a non-plan branch should exit with an error."""
    event_json: dict[str, Any] = {
        "comment": {"body": "/ship replan"},
        "issue": {
            "number": 3,
            "title": "PR",
            "body": "",
            "pull_request": {"url": "..."},
        },
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    branch_mock = MagicMock(returncode=0, stdout="feature/some-branch\n")

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
        "COMMENT_BODY": "/ship replan",
    }

    runner = CliRunner()
    with patch("subprocess.run", return_value=branch_mock):
        with runner.isolated_filesystem():
            result = runner.invoke(extract_github_event, env=env_vars)

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# extract_github_event CLI — implementation PR review (shipyard/ branch)
# ---------------------------------------------------------------------------


def test_extract_github_event_shipyard_branch_review(tmp_path: Path) -> None:
    event_json: dict[str, Any] = {
        "review": {"id": 55, "state": "changes_requested", "body": "Fix this"},
        "pull_request": {
            "number": 10,
            "body": "Closes #3\nCloses #4",
            "head": {"ref": "shipyard/epic-1-run-99"},
        },
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    inline_mock = MagicMock(returncode=0, stdout=json.dumps([]))
    issue3_mock = MagicMock(
        returncode=0,
        stdout=json.dumps({"number": 3, "title": "Task 3", "body": "body3"}),
    )
    issue4_mock = MagicMock(
        returncode=0,
        stdout=json.dumps({"number": 4, "title": "Task 4", "body": "body4"}),
    )

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", side_effect=[inline_mock, issue3_mock, issue4_mock]):
        with runner.isolated_filesystem() as isolated_dir:
            result = runner.invoke(extract_github_event, env=env_vars)
            prompt_path = Path(isolated_dir) / "prompt.txt"
            review_path = Path(isolated_dir) / "review-feedback.txt"

            assert result.exit_code == 0, result.output
            assert prompt_path.exists()
            assert review_path.exists()
            prompt_text = prompt_path.read_text()
            assert "Task 3" in prompt_text
            assert "Task 4" in prompt_text

    output_text = github_output_file.read_text()
    assert "has_review" in output_text
    assert "true" in output_text


def test_extract_github_event_shipyard_branch_no_closing_refs(tmp_path: Path) -> None:
    event_json: dict[str, Any] = {
        "review": {"id": 55, "state": "changes_requested", "body": "Fix this"},
        "pull_request": {
            "number": 10,
            "body": "No closing references here",
            "head": {"ref": "shipyard/epic-1-run-99"},
        },
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    inline_mock = MagicMock(returncode=0, stdout=json.dumps([]))

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", return_value=inline_mock):
        with runner.isolated_filesystem():
            result = runner.invoke(extract_github_event, env=env_vars)

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# extract_github_event CLI — review on unrecognised branch
# ---------------------------------------------------------------------------


def test_extract_github_event_plan_branch_review_no_closing_refs(tmp_path: Path) -> None:
    """Plan-branch review with no closing references in the PR body should exit with error."""
    event_json: dict[str, Any] = {
        "review": {"id": 77, "state": "changes_requested", "body": "Fix it"},
        "pull_request": {
            "number": 8,
            "body": "No closing references here",
            "head": {"ref": "plan/i3"},
        },
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    inline_mock = MagicMock(returncode=0, stdout=json.dumps([]))

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", return_value=inline_mock):
        with runner.isolated_filesystem():
            result = runner.invoke(extract_github_event, env=env_vars)

    assert result.exit_code != 0


def test_extract_github_event_unrecognised_branch(tmp_path: Path) -> None:
    event_json: dict[str, Any] = {
        "review": {"id": 1, "state": "changes_requested", "body": "nope"},
        "pull_request": {
            "number": 5,
            "body": "Closes #2",
            "head": {"ref": "feature/something-random"},
        },
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    inline_mock = MagicMock(returncode=0, stdout=json.dumps([]))

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", return_value=inline_mock):
        with runner.isolated_filesystem():
            result = runner.invoke(extract_github_event, env=env_vars)

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# extract_github_event CLI — ISSUE_NUMBER fallback
# ---------------------------------------------------------------------------


def test_extract_github_event_issue_number_fallback(tmp_path: Path) -> None:
    """Unknown event type with ISSUE_NUMBER set writes prompt.txt from the issue API."""
    event_json: dict[str, Any] = {"action": "labeled"}
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    issue_mock = MagicMock(
        returncode=0,
        stdout=json.dumps({"number": 99, "title": "Fallback Issue", "body": "Details"}),
    )

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
        "ISSUE_NUMBER": "99",
    }

    runner = CliRunner()
    with patch("subprocess.run", return_value=issue_mock):
        with runner.isolated_filesystem() as isolated_dir:
            result = runner.invoke(extract_github_event, env=env_vars)
            prompt_path = Path(isolated_dir) / "prompt.txt"

            assert result.exit_code == 0, result.output
            assert prompt_path.exists()
            assert "Fallback Issue" in prompt_path.read_text()

    output_text = github_output_file.read_text()
    assert "has_review" in output_text
    assert "false" in output_text
