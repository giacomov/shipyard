"""Tests for shipyard.utils.github_event."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from shipyard.utils.github_event import (
    extract_github_event,
    extract_issue_from_pr_review,
    fetch_issue_context,
    parse_github_event,
)

# ---------------------------------------------------------------------------
# parse_github_event
# ---------------------------------------------------------------------------


def test_parse_github_event_issues_labeled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    event_json: dict[str, Any] = {"issue": {"number": 42}, "label": {"name": "plan"}}

    issue_number, repo = parse_github_event(event_json)

    assert issue_number == 42
    assert repo == "owner/repo"


def test_parse_github_event_pr_review(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    event_json: dict[str, Any] = {
        "review": {"state": "CHANGES_REQUESTED"},
        "pull_request": {"body": "Closes #7"},
    }

    issue_number, repo = parse_github_event(event_json)

    assert issue_number == 7
    assert repo == "owner/repo"


def test_parse_github_event_pr_review_no_closing_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    event_json: dict[str, Any] = {
        "review": {},
        "pull_request": {"body": "No references here"},
    }

    with pytest.raises(ValueError):
        parse_github_event(event_json)


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

    result = extract_issue_from_pr_review(event_json, "owner/repo")

    assert result == 123


def test_extract_issue_from_pr_review_not_found() -> None:
    event_json: dict[str, Any] = {"pull_request": {"body": "No references"}}

    with pytest.raises(ValueError):
        extract_issue_from_pr_review(event_json, "owner/repo")


# ---------------------------------------------------------------------------
# extract_github_event CLI — issues.labeled
# ---------------------------------------------------------------------------


def test_extract_github_event_issues_labeled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_json: dict[str, Any] = {
        "issue": {"number": 10, "title": "My Epic", "body": "Do the work"},
        "label": {"name": "plan"},
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output_file))

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            extract_github_event,
            env={
                "GITHUB_EVENT_PATH": str(event_file),
                "GITHUB_REPOSITORY": "owner/repo",
                "GITHUB_OUTPUT": str(github_output_file),
            },
        )

    assert result.exit_code == 0, result.output
    output_text = github_output_file.read_text()
    assert "issue_number" in output_text
    assert "10" in output_text


def test_extract_github_event_issues_labeled_writes_prompt_txt(
    tmp_path: Path,
) -> None:
    event_json: dict[str, Any] = {
        "issue": {"number": 10, "title": "My Epic", "body": "Do the work"},
        "label": {"name": "plan"},
    }
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
    with runner.isolated_filesystem() as isolated_dir:
        result = runner.invoke(extract_github_event, env=env_vars)
        prompt_path = Path(isolated_dir) / "prompt.txt"
        assert result.exit_code == 0, result.output
        assert prompt_path.exists(), "prompt.txt was not written"
        prompt_text = prompt_path.read_text()
        assert "My Epic" in prompt_text
        assert "Do the work" in prompt_text


# ---------------------------------------------------------------------------
# extract_github_event CLI — pull_request_review
# ---------------------------------------------------------------------------


def test_extract_github_event_pr_review(
    tmp_path: Path,
) -> None:
    event_json: dict[str, Any] = {
        "review": {"state": "CHANGES_REQUESTED", "body": "Please add tests"},
        "pull_request": {"number": 3, "body": "Closes #7"},
    }
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event_json))

    github_output_file = tmp_path / "github_output.txt"
    github_output_file.write_text("")

    gh_response: dict[str, Any] = {"number": 7, "title": "Fix the thing", "body": "Details"}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps(gh_response)

    env_vars: dict[str, str] = {
        "GITHUB_EVENT_PATH": str(event_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_OUTPUT": str(github_output_file),
    }

    runner = CliRunner()
    with patch("subprocess.run", return_value=mock_result):
        with runner.isolated_filesystem() as isolated_dir:
            result = runner.invoke(extract_github_event, env=env_vars)
            prompt_path = Path(isolated_dir) / "prompt.txt"
            review_path = Path(isolated_dir) / "review-feedback.txt"

            assert result.exit_code == 0, result.output
            assert prompt_path.exists(), "prompt.txt was not written"
            assert review_path.exists(), "review-feedback.txt was not written"
            assert "Please add tests" in review_path.read_text()

    output_text = github_output_file.read_text()
    assert "has_review" in output_text
    assert "true" in output_text


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
