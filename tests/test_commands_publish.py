"""Tests for shipyard.commands.publish."""

import json
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from shipyard.commands.publish import publish_execution

_WORK_JSON = json.dumps(
    {
        "epic_id": "42",
        "title": "T",
        "description": "",
        "tasks": {
            "5": {"task_id": "5", "title": "T5", "description": "", "blocked_by": []},
            "6": {"task_id": "6", "title": "T6", "description": "", "blocked_by": []},
        },
    }
)


def _write_work(tmp_path: Any) -> str:
    work_file = tmp_path / "work.json"
    work_file.write_text(_WORK_JSON)
    return str(work_file)


def _write_results(tmp_path: Any, successful: list[str], failed: list[str] | None = None) -> str:
    results_file = tmp_path / "shipyard-results.json"
    results_file.write_text(json.dumps({"successful": successful, "failed": failed or []}))
    return str(results_file)


# ---------------------------------------------------------------------------
# Missing input file
# ---------------------------------------------------------------------------


def test_publish_missing_input_file(tmp_path: Any) -> None:
    results_file = _write_results(tmp_path, ["1", "2"])

    runner = CliRunner()
    result = runner.invoke(
        publish_execution, ["--branch", "my-branch", "--results-file", results_file]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# No successful tasks — skip push and PR
# ---------------------------------------------------------------------------


def test_publish_no_successful_tasks(tmp_path: Any) -> None:
    work_file = _write_work(tmp_path)
    results_file = _write_results(tmp_path, [])

    runner = CliRunner()
    with (
        patch("shipyard.commands.publish.push") as mock_push,
        patch("shipyard.commands.publish.create_pull_request") as mock_pr,
    ):
        result = runner.invoke(
            publish_execution,
            ["--branch", "my-branch", "-i", work_file, "--results-file", results_file],
        )

    assert result.exit_code == 0
    mock_push.assert_not_called()
    mock_pr.assert_not_called()
    assert "skipping" in result.output


# ---------------------------------------------------------------------------
# Successful tasks — push and create PR
# ---------------------------------------------------------------------------


def test_publish_pushes_and_creates_pr(tmp_path: Any) -> None:
    work_file = _write_work(tmp_path)
    results_file = _write_results(tmp_path, ["5", "6"])

    runner = CliRunner()
    with (
        patch("shipyard.commands.publish.push") as mock_push,
        patch(
            "shipyard.commands.publish.create_pull_request",
            return_value="https://github.com/owner/repo/pull/99",
        ) as mock_pr,
        patch("shipyard.commands.publish.resolve_repo", return_value="owner/repo"),
    ):
        result = runner.invoke(
            publish_execution,
            ["--branch", "my-branch", "-i", work_file, "--results-file", results_file],
        )

    assert result.exit_code == 0
    mock_push.assert_called_once_with("my-branch", set_upstream=True)
    mock_pr.assert_called_once()
    pr_args = mock_pr.call_args[0]
    assert pr_args[0] == "owner/repo"
    assert pr_args[1] == "my-branch"
    assert "epic #42" in pr_args[2]
    assert "Closes #5" in pr_args[3]
    assert "Closes #6" in pr_args[3]
    assert "PR created" in result.output
