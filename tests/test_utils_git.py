"""Tests for shipyard.utils.git."""

from unittest.mock import MagicMock, patch

import pytest

from shipyard.utils.git import (
    add,
    checkout_branch,
    checkout_new_branch,
    commit,
    fetch,
    git,
    push,
    reset_hard,
)


def _ok(stdout: str = "") -> MagicMock:
    """Return a mock subprocess result with returncode=0."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


def _fail(stderr: str = "error") -> MagicMock:
    """Return a mock subprocess result with returncode=1."""
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# git() base wrapper
# ---------------------------------------------------------------------------


def test_git_returns_stripped_stdout() -> None:
    with patch("subprocess.run", return_value=_ok("abc123\n")) as mock_run:
        result = git(["rev-parse", "HEAD"])

    assert result == "abc123"
    mock_run.assert_called_once_with(["git", "rev-parse", "HEAD"], capture_output=True, text=True)


def test_git_raises_runtime_error_on_failure() -> None:
    with patch("subprocess.run", return_value=_fail("not a git repo")):
        with pytest.raises(RuntimeError, match="git command failed"):
            git(["status"])


def test_git_error_message_includes_args_and_stderr() -> None:
    with patch("subprocess.run", return_value=_fail("fatal: bad object")):
        with pytest.raises(RuntimeError) as exc_info:
            git(["show", "deadbeef"])

    assert "show" in str(exc_info.value)
    assert "fatal: bad object" in str(exc_info.value)


# ---------------------------------------------------------------------------
# checkout_new_branch()
# ---------------------------------------------------------------------------


def test_checkout_new_branch_calls_git() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        checkout_new_branch("feature/my-branch")

    mock_run.assert_called_once_with(
        ["git", "checkout", "-b", "feature/my-branch"], capture_output=True, text=True
    )


# ---------------------------------------------------------------------------
# checkout_branch()
# ---------------------------------------------------------------------------


def test_checkout_branch_calls_git() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        checkout_branch("main")

    mock_run.assert_called_once_with(["git", "checkout", "main"], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# fetch()
# ---------------------------------------------------------------------------


def test_fetch_defaults_to_origin() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        fetch()

    mock_run.assert_called_once_with(["git", "fetch", "origin"], capture_output=True, text=True)


def test_fetch_uses_given_remote() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        fetch("upstream")

    mock_run.assert_called_once_with(["git", "fetch", "upstream"], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# add()
# ---------------------------------------------------------------------------


def test_add_stages_paths() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        add(["foo.py", "bar.py"])

    mock_run.assert_called_once_with(
        ["git", "add", "foo.py", "bar.py"], capture_output=True, text=True
    )


# ---------------------------------------------------------------------------
# commit()
# ---------------------------------------------------------------------------


def test_commit_uses_message() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        commit("fix: correct typo")

    mock_run.assert_called_once_with(
        ["git", "commit", "-m", "fix: correct typo"], capture_output=True, text=True
    )


# ---------------------------------------------------------------------------
# push()
# ---------------------------------------------------------------------------


def test_push_without_upstream() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        push("my-branch")

    mock_run.assert_called_once_with(
        ["git", "push", "origin", "my-branch"], capture_output=True, text=True
    )


def test_push_with_upstream() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        push("my-branch", set_upstream=True)

    mock_run.assert_called_once_with(
        ["git", "push", "-u", "origin", "my-branch"], capture_output=True, text=True
    )


def test_push_custom_remote() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        push("my-branch", remote="upstream")

    mock_run.assert_called_once_with(
        ["git", "push", "upstream", "my-branch"], capture_output=True, text=True
    )


# ---------------------------------------------------------------------------
# reset_hard()
# ---------------------------------------------------------------------------


def test_reset_hard_passes_ref() -> None:
    with patch("subprocess.run", return_value=_ok()) as mock_run:
        reset_hard("abc123")

    mock_run.assert_called_once_with(
        ["git", "reset", "--hard", "abc123"], capture_output=True, text=True
    )


def test_reset_hard_raises_on_failure() -> None:
    with patch("subprocess.run", return_value=_fail("bad ref")):
        with pytest.raises(RuntimeError, match="git command failed"):
            reset_hard("deadbeef")
