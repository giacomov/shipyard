from unittest.mock import patch
from scripts.find_epic_work import (
    parse_closing_references,
    find_unblocked_sub_issues,
    build_work_json,
    set_output,
    resolve_epic_number,
)


def test_parse_closing_references_standard():
    body = "Closes #42\nFixes #7\nResolves #100"
    assert parse_closing_references(body) == [42, 7, 100]


def test_parse_closing_references_empty():
    assert parse_closing_references("No references here") == []


def test_parse_closing_references_case_insensitive():
    assert parse_closing_references("CLOSES #5") == [5]


@patch("scripts.find_epic_work.gh_get")
def test_find_unblocked_filters_open_blockers(mock_get):
    # Issue 2 has an open blocker, issue 3 is unblocked
    def side_effect(path):
        if "sub_issues" in path:
            return [
                {"number": 2, "state": "open", "title": "Task A", "body": ""},
                {"number": 3, "state": "open", "title": "Task B", "body": ""},
                {"number": 4, "state": "closed", "title": "Task C", "body": ""},
            ]
        if "2/dependencies" in path:
            return [{"state": "open", "number": 1}]  # open blocker
        if "3/dependencies" in path:
            return []  # no blockers
        return []
    mock_get.side_effect = side_effect
    result = find_unblocked_sub_issues(10, "owner/repo")
    assert len(result) == 1
    assert result[0]["number"] == 3


def test_build_work_json_structure():
    epic = {"number": 10, "title": "My Epic", "body": "Do stuff"}
    issues = [{"number": 5, "title": "Task A", "body": "Spec A"}]
    result = build_work_json(epic, issues, "owner/repo")
    assert result["epic_number"] == 10
    assert result["repo"] == "owner/repo"
    assert len(result["issues"]) == 1
    assert result["issues"][0]["number"] == 5


def test_set_output_to_stdout_when_no_github_output(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    set_output("has_work", "true")
    captured = capsys.readouterr()
    assert "has_work" in captured.out


@patch("scripts.find_epic_work.gh_graphql")
def test_resolve_epic_pr_event_graphql_path(mock_gql, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    mock_gql.return_value = {
        "repository": {
            "issue": {
                "parent": {
                    "number": 10,
                    "labels": {"nodes": [{"name": "in-progress"}]},
                }
            }
        }
    }
    result = resolve_epic_number("pull_request", None, "Closes #5", "owner", "repo")
    assert result == 10


def test_resolve_epic_issues_event():
    result = resolve_epic_number("issues", 7, "", "owner", "repo")
    assert result == 7


def test_resolve_epic_workflow_dispatch():
    result = resolve_epic_number("workflow_dispatch", 15, "", "owner", "repo")
    assert result == 15
