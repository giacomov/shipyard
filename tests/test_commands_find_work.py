from unittest.mock import patch
from click.testing import CliRunner
from shipyard.commands.find_work import find_work


def test_find_work_errors_without_env_vars(monkeypatch):
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
    # Epic issue fetch + sub_issues (empty)
    mock_gh_get.side_effect = [
        {"number": 10, "title": "My Epic", "body": ""},
        [],
    ]
    runner = CliRunner()
    result = runner.invoke(find_work)
    assert result.exit_code == 0
    mock_set_output.assert_called_with("has_work", "false")
