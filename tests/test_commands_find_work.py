import json
from unittest.mock import patch

from click.testing import CliRunner

from shipyard.commands.find_work import find_work


def test_find_work_errors_without_required_flags():
    runner = CliRunner()
    result = runner.invoke(find_work)
    assert result.exit_code != 0


@patch("shipyard.commands.find_work.gh_get")
@patch("shipyard.commands.find_work.set_output")
def test_find_work_no_unblocked_sets_has_work_false(mock_set_output, mock_gh_get):
    # Epic issue fetch + sub_issues (empty)
    mock_gh_get.side_effect = [
        {"number": 10, "title": "My Epic", "body": ""},
        [],
    ]
    runner = CliRunner()
    result = runner.invoke(
        find_work,
        ["--repo", "owner/repo", "--issue-number", "10"],
    )
    assert result.exit_code == 0
    mock_set_output.assert_called_with("has_work", "false")


@patch("shipyard.commands.find_work.resolve_epic_number", return_value=None)
@patch("shipyard.commands.find_work.set_output")
def test_find_work_no_epic_exits_early(mock_set_output, mock_resolve):
    runner = CliRunner()
    result = runner.invoke(find_work, ["--repo", "owner/repo", "--issue-number", "10"])
    assert result.exit_code == 0
    mock_set_output.assert_any_call("has_work", "false")
    mock_set_output.assert_any_call("epic_in_progress", "false")


@patch("shipyard.commands.find_work.resolve_epic_number", return_value=10)
@patch("shipyard.commands.find_work.set_output")
@patch("shipyard.commands.find_work.gh_get")
def test_find_work_with_unblocked_work_sets_work_json(mock_gh_get, mock_set_output, mock_resolve):
    # gh_get call order: epic issue, sub_issues, blocked_by for issue 5
    mock_gh_get.side_effect = [
        {"number": 10, "title": "Epic", "body": "Desc"},
        [{"number": 5, "state": "open", "title": "Task A", "body": "Do A"}],
        [],  # no blockers for issue 5
    ]
    runner = CliRunner()
    result = runner.invoke(find_work, ["--repo", "owner/repo", "--issue-number", "10"])
    assert result.exit_code == 0

    mock_set_output.assert_any_call("has_work", "true")

    work_json_calls = [c for c in mock_set_output.call_args_list if c.args[0] == "work_json"]
    assert len(work_json_calls) == 1
    work_data = json.loads(work_json_calls[0].args[1])
    assert "5" in work_data["tasks"]
    assert work_data["tasks"]["5"]["title"] == "Task A"
