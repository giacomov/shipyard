import json
import os
import tempfile
from unittest.mock import patch

import pytest

from shipyard.commands.find_work import (
    build_subtask_list,
    find_unblocked_sub_issues,
    gh,
    gh_get,
    gh_graphql,
    parse_closing_references,
    resolve_epic_number,
    set_output,
)

# ---------------------------------------------------------------------------
# parse_closing_references
# ---------------------------------------------------------------------------


def test_parse_closing_references_standard():
    body = "Closes #42\nFixes #7\nResolves #100"
    assert parse_closing_references(body) == [42, 7, 100]


def test_parse_closing_references_empty():
    assert parse_closing_references("No references here") == []


def test_parse_closing_references_case_insensitive():
    assert parse_closing_references("CLOSES #5") == [5]


def test_parse_closing_references_close_singular():
    assert parse_closing_references("close #3") == [3]


def test_parse_closing_references_fixes_plural():
    assert parse_closing_references("fixes #8") == [8]


# ---------------------------------------------------------------------------
# gh / gh_get / gh_graphql helpers
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess.run")
def test_gh_returns_trimmed_stdout(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "  hello world  \n"
    assert gh(["issue", "list"]) == "hello world"


@patch("shipyard.utils.gh.subprocess.run")
def test_gh_raises_on_nonzero(mock_run):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "something went wrong"
    with pytest.raises(RuntimeError, match="something went wrong"):
        gh(["api", "bad-path"])


@patch("shipyard.commands.find_work.gh")
def test_gh_get_parses_json(mock_gh):
    mock_gh.return_value = '{"number": 7}'
    result = gh_get("repos/o/r/issues/7")
    assert result == {"number": 7}


@patch("shipyard.commands.find_work.gh")
def test_gh_graphql_returns_data(mock_gh):
    mock_gh.return_value = json.dumps({"data": {"repository": {"issue": None}}, "errors": None})
    result = gh_graphql("query Q { }", {"owner": "o", "repo": "r", "number": 1})
    assert "repository" in result


@patch("shipyard.commands.find_work.gh")
def test_gh_graphql_raises_on_errors(mock_gh):
    mock_gh.return_value = json.dumps({"errors": [{"message": "Field not found"}]})
    with pytest.raises(RuntimeError, match="Field not found"):
        gh_graphql("query Q { }", {})


# ---------------------------------------------------------------------------
# set_output
# ---------------------------------------------------------------------------


def test_set_output_to_stdout_when_no_github_output(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    set_output("has_work", "true")
    captured = capsys.readouterr()
    assert "has_work" in captured.out


def test_set_output_writes_to_file(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        monkeypatch.setenv("GITHUB_OUTPUT", path)
        set_output("work_json", '{"epic_number": 1}')
        content = open(path).read()
        assert "work_json" in content
        assert '{"epic_number": 1}' in content
        # Must use heredoc delimiter format so multiline values are safe
        assert "<<" in content
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# resolve_epic_number
# ---------------------------------------------------------------------------


def test_resolve_epic_direct_mode():
    assert resolve_epic_number(7, "", "owner", "repo") == 7


def test_resolve_epic_direct_mode_ignores_pr_body():
    assert resolve_epic_number(15, "Closes #99", "owner", "repo") == 15


def test_resolve_epic_pr_mode_no_closing_references_returns_none():
    result = resolve_epic_number(None, "no refs here", "owner", "repo")
    assert result is None


@patch("shipyard.commands.find_work.gh_graphql")
def test_resolve_epic_pr_mode_graphql_path(mock_gql):
    mock_gql.return_value = {"repository": {"issue": {"parent": {"number": 10}}}}
    result = resolve_epic_number(None, "Closes #5", "owner", "repo")
    assert result == 10


@patch("shipyard.commands.find_work.gh_graphql")
def test_resolve_epic_pr_mode_no_parent_falls_back_to_scan(mock_gql):
    mock_gql.return_value = {"repository": {"issue": {"parent": None}}}
    candidates = [{"number": 99}]
    with (
        patch("shipyard.commands.find_work.gh") as mock_gh,
        patch("shipyard.commands.find_work.gh_get") as mock_get,
    ):
        mock_gh.return_value = json.dumps(candidates)
        # Issue #5 is a sub-issue of epic #99
        mock_get.return_value = [{"number": 5}]
        result = resolve_epic_number(None, "Closes #5", "owner", "repo")
    assert result == 99


@patch("shipyard.commands.find_work.gh_graphql")
def test_resolve_epic_pr_mode_graphql_error_falls_back(mock_gql):
    mock_gql.side_effect = RuntimeError("GraphQL unavailable")
    candidates = [{"number": 42}]
    with (
        patch("shipyard.commands.find_work.gh") as mock_gh,
        patch("shipyard.commands.find_work.gh_get") as mock_get,
    ):
        mock_gh.return_value = json.dumps(candidates)
        mock_get.return_value = [{"number": 5}]
        result = resolve_epic_number(None, "Closes #5", "owner", "repo")
    assert result == 42


# ---------------------------------------------------------------------------
# find_unblocked_sub_issues
# ---------------------------------------------------------------------------


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


@patch("shipyard.commands.find_work.gh_get")
def test_find_unblocked_ignores_closed_sub_issues(mock_get):
    def side_effect(path):
        if "sub_issues" in path:
            return [{"number": 1, "state": "closed", "title": "Done", "body": ""}]
        return []

    mock_get.side_effect = side_effect
    assert find_unblocked_sub_issues(10, "owner/repo") == []


@patch("shipyard.commands.find_work.gh_get")
def test_find_unblocked_closed_blocker_does_not_block(mock_get):
    def side_effect(path):
        if "sub_issues" in path:
            return [{"number": 7, "state": "open", "title": "T", "body": ""}]
        if "7/dependencies" in path:
            return [{"state": "closed", "number": 6}]
        return []

    mock_get.side_effect = side_effect
    result = find_unblocked_sub_issues(10, "owner/repo")
    assert result[0]["number"] == 7


# ---------------------------------------------------------------------------
# build_subtask_list
# ---------------------------------------------------------------------------


def test_build_subtask_list_structure():
    epic = {"number": 10, "title": "My Epic", "body": "Do stuff"}
    issues = [{"number": 5, "title": "Task A", "body": "Spec A"}]
    result = build_subtask_list(epic, issues)
    assert result.epic_id == "10"
    assert result.title == "My Epic"
    assert result.description == "Do stuff"
    assert len(result.tasks) == 1
    assert result.tasks["5"].task_id == "5"
    assert result.tasks["5"].title == "Task A"
    assert result.tasks["5"].description == "Spec A"


def test_build_subtask_list_none_body_becomes_empty_string():
    epic = {"number": 1, "title": "E", "body": None}
    issues = [{"number": 2, "title": "T", "body": None}]
    result = build_subtask_list(epic, issues)
    assert result.description == ""
    assert result.tasks["2"].description == ""


# ---------------------------------------------------------------------------
# find-work CLI command — flag guards
# ---------------------------------------------------------------------------


def test_find_work_missing_repo():
    from click.testing import CliRunner

    from shipyard.commands.find_work import find_work

    runner = CliRunner()
    result = runner.invoke(find_work, ["--issue-number", "5"])
    assert result.exit_code != 0
    assert "--repo" in result.output


def test_find_work_missing_both_issue_number_and_pr_body():
    from click.testing import CliRunner

    from shipyard.commands.find_work import find_work

    runner = CliRunner()
    result = runner.invoke(find_work, ["--repo", "owner/repo"])
    assert result.exit_code != 0
    assert "--issue-number" in result.output or "--pr-body" in result.output


# ---------------------------------------------------------------------------
# resolve_epic_number — sub-issue scan fallback, multi-candidate branches
# ---------------------------------------------------------------------------


@patch("shipyard.commands.find_work.gh_graphql")
def test_resolve_epic_scan_finds_on_second_candidate(mock_gql):
    mock_gql.side_effect = RuntimeError("GraphQL unavailable")
    candidates = [{"number": 10}, {"number": 20}]

    def gh_get_side_effect(path: str):
        if "10/sub_issues" in path:
            return []  # issue #5 not a sub of candidate 10
        if "20/sub_issues" in path:
            return [{"number": 5}]  # issue #5 is a sub of candidate 20
        return []

    with (
        patch("shipyard.commands.find_work.gh") as mock_gh,
        patch("shipyard.commands.find_work.gh_get", side_effect=gh_get_side_effect),
    ):
        mock_gh.return_value = json.dumps(candidates)
        result = resolve_epic_number(None, "Closes #5", "owner", "repo")

    assert result == 20


@patch("shipyard.commands.find_work.gh_graphql")
def test_resolve_epic_scan_all_candidates_fail(mock_gql):
    mock_gql.side_effect = RuntimeError("GraphQL unavailable")
    candidates = [{"number": 10}, {"number": 20}]

    with (
        patch("shipyard.commands.find_work.gh") as mock_gh,
        patch("shipyard.commands.find_work.gh_get") as mock_get,
    ):
        mock_gh.return_value = json.dumps(candidates)
        mock_get.return_value = []  # no candidate contains issue #5
        result = resolve_epic_number(None, "Closes #5", "owner", "repo")

    assert result is None
