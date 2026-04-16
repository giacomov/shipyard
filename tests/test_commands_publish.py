"""Tests for shipyard.commands.publish."""

import json
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from shipyard.commands.publish import publish_execution

_WORK_JSON = json.dumps({"repo": "owner/repo", "epic_number": 42, "epic_title": "T", "issues": []})


def _write_results(tmp_path: Any, successful: list[int], failed: list[int] | None = None) -> str:
    results_file = tmp_path / "shipyard-results.json"
    results_file.write_text(json.dumps({"successful": successful, "failed": failed or []}))
    return str(results_file)


# ---------------------------------------------------------------------------
# Missing WORK_JSON
# ---------------------------------------------------------------------------


def test_publish_missing_work_json(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.delenv("WORK_JSON", raising=False)
    results_file = _write_results(tmp_path, [1, 2])

    runner = CliRunner()
    result = runner.invoke(
        publish_execution, ["--branch", "my-branch", "--results-file", results_file]
    )
    assert result.exit_code != 0
    assert "WORK_JSON" in result.output


# ---------------------------------------------------------------------------
# No successful issues — skip push and PR
# ---------------------------------------------------------------------------


def test_publish_no_successful_issues(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("WORK_JSON", _WORK_JSON)
    results_file = _write_results(tmp_path, [])

    runner = CliRunner()
    with (
        patch("shipyard.commands.publish.push") as mock_push,
        patch("shipyard.commands.publish.create_pull_request") as mock_pr,
    ):
        result = runner.invoke(
            publish_execution, ["--branch", "my-branch", "--results-file", results_file]
        )

    assert result.exit_code == 0
    mock_push.assert_not_called()
    mock_pr.assert_not_called()
    assert "skipping" in result.output


# ---------------------------------------------------------------------------
# Successful issues — push and create PR
# ---------------------------------------------------------------------------


def test_publish_pushes_and_creates_pr(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setenv("WORK_JSON", _WORK_JSON)
    results_file = _write_results(tmp_path, [5, 6])

    runner = CliRunner()
    with (
        patch("shipyard.commands.publish.push") as mock_push,
        patch(
            "shipyard.commands.publish.create_pull_request",
            return_value="https://github.com/owner/repo/pull/99",
        ) as mock_pr,
    ):
        result = runner.invoke(
            publish_execution, ["--branch", "my-branch", "--results-file", results_file]
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
