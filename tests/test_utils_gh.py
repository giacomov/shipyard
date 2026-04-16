"""Tests for shipyard.utils.gh."""

import os
from unittest.mock import MagicMock, patch

import pytest

from shipyard.utils.gh import gh, parse_closing_references, resolve_repo, set_github_output

# ---------------------------------------------------------------------------
# gh()
# ---------------------------------------------------------------------------


def test_gh_returns_stripped_stdout() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "  owner/repo\n"

    with patch("subprocess.run", return_value=mock_result):
        result = gh(["repo", "view", "--json", "nameWithOwner"])

    assert result == "owner/repo"


def test_gh_raises_runtime_error_on_failure() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "not found"

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="gh command failed"):
            gh(["repo", "view"])


def test_gh_dry_run_returns_empty_string(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("subprocess.run") as mock_run:
        result = gh(["issue", "create", "--title", "Test"], dry_run=True)

    assert result == ""
    mock_run.assert_not_called()
    captured = capsys.readouterr()
    assert "dry-run" in captured.out
    assert "issue" in captured.out


def test_gh_dry_run_with_label(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("subprocess.run") as mock_run:
        result = gh(["api", "some/path"], dry_run=True, dry_label="create sub-issue")

    assert result == ""
    mock_run.assert_not_called()
    captured = capsys.readouterr()
    assert "create sub-issue" in captured.out


def test_gh_error_message_includes_args() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 2
    mock_result.stderr = "bad arguments"

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError) as exc_info:
            gh(["pr", "create", "--title", "x"])

    assert "pr" in str(exc_info.value)
    assert "bad arguments" in str(exc_info.value)


# ---------------------------------------------------------------------------
# resolve_repo()
# ---------------------------------------------------------------------------


def test_resolve_repo_returns_flag_if_set() -> None:
    result = resolve_repo(repo_flag="myorg/myrepo")
    assert result == "myorg/myrepo"


def test_resolve_repo_calls_gh_when_no_flag() -> None:
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "owner/repo\n"

    with patch("subprocess.run", return_value=mock_result):
        result = resolve_repo()

    assert result == "owner/repo"


def test_resolve_repo_returns_placeholder_on_dry_run_empty() -> None:
    result = resolve_repo(dry_run=True)
    assert result == "<owner>/<repo>"


# ---------------------------------------------------------------------------
# set_github_output()
# ---------------------------------------------------------------------------


def test_set_github_output_writes_heredoc(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_file = os.path.join(str(tmp_path), "github_output.txt")  # type: ignore[arg-type]
    open(output_file, "w").close()
    monkeypatch.setenv("GITHUB_OUTPUT", output_file)

    set_github_output("my_key", "hello world")

    content = open(output_file).read()
    assert "my_key<<EOF_MY_KEY\nhello world\nEOF_MY_KEY\n" in content


def test_set_github_output_prints_locally_when_no_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    set_github_output("work_json", '{"key": "val"}')

    captured = capsys.readouterr()
    assert "work_json" in captured.out
    assert '{"key": "val"}' in captured.out


# ---------------------------------------------------------------------------
# parse_closing_references()
# ---------------------------------------------------------------------------


def test_parse_closing_references_basic() -> None:
    assert parse_closing_references("Closes #42") == [42]


def test_parse_closing_references_multiple() -> None:
    body = "Closes #1\nFixes #2\nResolves #3"
    assert parse_closing_references(body) == [1, 2, 3]


def test_parse_closing_references_plural_forms() -> None:
    body = "close #10 fixes #20 resolve #30"
    result = parse_closing_references(body)
    assert 10 in result
    assert 20 in result
    assert 30 in result


def test_parse_closing_references_case_insensitive() -> None:
    assert parse_closing_references("CLOSES #99") == [99]


def test_parse_closing_references_no_match() -> None:
    assert parse_closing_references("No references here") == []


def test_parse_closing_references_ignores_plain_hash() -> None:
    # "#42" alone without a keyword should not match
    assert parse_closing_references("See #42 for details") == []
