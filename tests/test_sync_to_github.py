import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from shipyard.commands.sync import (
    IssueRef,
    add_blocked_by,
    add_sub_issue,
    create_issue,
    gh,
    resolve_repo,
    run_sync,
    task_body,
    validate,
)
from shipyard.schemas import Subtask, SubtaskList

# ---------------------------------------------------------------------------
# gh helper
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess")
def test_gh_runs_command(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "output\n"
    result = gh(["issue", "list"])
    assert result == "output"
    mock_subprocess.run.assert_called_once()


@patch("shipyard.utils.gh.subprocess")
def test_gh_raises_on_nonzero(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "error msg"
    mock_subprocess.run.return_value.stdout = ""
    with pytest.raises(RuntimeError, match="gh command failed"):
        gh(["issue", "create", "--title", "x"])


def test_gh_sim_mode_issue_create_returns_mock_url(monkeypatch, capsys):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    result = gh(["issue", "create", "--repo", "owner/repo", "--title", "T", "--body", "B"])
    assert "owner/repo/issues/999" in result
    out = capsys.readouterr().out
    assert "[sim]" in out
    assert "issue create" in out


def test_gh_sim_mode_pr_create_returns_mock_url(monkeypatch):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    result = gh(
        [
            "pr",
            "create",
            "--repo",
            "owner/repo",
            "--title",
            "T",
            "--body",
            "B",
            "--base",
            "main",
            "--head",
            "feat",
        ]
    )
    assert "owner/repo/pull/999" in result


def test_gh_sim_mode_api_post_intercepted(monkeypatch, capsys):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    result = gh(
        [
            "api",
            "repos/owner/repo/issues/1/sub_issues",
            "--method",
            "POST",
            "-F",
            "sub_issue_id=123",
        ]
    )
    assert result == "{}"
    out = capsys.readouterr().out
    assert "[sim]" in out


def test_gh_sim_mode_read_only_not_intercepted(monkeypatch):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "output\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = gh(["issue", "list", "--repo", "owner/repo"])
    assert result == "output"
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_repo
# ---------------------------------------------------------------------------


def test_resolve_repo_uses_flag():
    assert resolve_repo("myorg/myrepo") == "myorg/myrepo"


@patch("shipyard.utils.gh.gh", return_value="owner/detected")
def test_resolve_repo_auto_detects(mock_gh):
    assert resolve_repo(None) == "owner/detected"


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess")
def test_create_issue_parses_number_from_url(mock_subprocess):
    mock_subprocess.run.side_effect = [
        type(
            "R",
            (),
            {"returncode": 0, "stdout": "https://github.com/owner/repo/issues/42\n", "stderr": ""},
        )(),
        type("R", (), {"returncode": 0, "stdout": "123456\n", "stderr": ""})(),
    ]
    ref = create_issue("owner/repo", "My Title", "My Body")
    assert ref.number == 42
    assert ref.database_id == 123456
    assert ref.url == "https://github.com/owner/repo/issues/42"


def test_create_issue_sim_mode_makes_no_subprocess_calls(monkeypatch):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    with patch("subprocess.run") as mock_run:
        ref = create_issue("owner/repo", "Title", "Body")
    mock_run.assert_not_called()
    assert ref.number == 999
    assert ref.database_id == 999


@patch("shipyard.utils.gh.subprocess")
def test_create_issue_raises_on_bad_url(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "not-a-url\n"
    mock_subprocess.run.return_value.stderr = ""
    with pytest.raises(RuntimeError, match="Unexpected gh issue create output"):
        create_issue("owner/repo", "T", "B")


# ---------------------------------------------------------------------------
# add_sub_issue
# ---------------------------------------------------------------------------


def test_add_sub_issue_sim_mode_prints(monkeypatch, capsys):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    add_sub_issue("owner/repo", 1, 999, 5)
    out = capsys.readouterr().out
    assert "[sim]" in out


# ---------------------------------------------------------------------------
# add_blocked_by
# ---------------------------------------------------------------------------


@patch("shipyard.utils.gh.subprocess")
def test_add_blocked_by_404_is_soft_failure(mock_subprocess, capsys):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "404 Not Found"
    mock_subprocess.run.return_value.stdout = ""
    add_blocked_by("owner/repo", 5, 500, 3, 300)
    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "dependencies API" in captured.out


@patch("shipyard.utils.gh.subprocess")
def test_add_blocked_by_reraises_non_404(mock_subprocess):
    mock_subprocess.run.return_value.returncode = 1
    mock_subprocess.run.return_value.stderr = "500 Internal Server Error"
    mock_subprocess.run.return_value.stdout = ""
    with pytest.raises(RuntimeError):
        add_blocked_by("owner/repo", 5, 500, 3, 300)


def test_add_blocked_by_sim_mode(monkeypatch, capsys):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    add_blocked_by("owner/repo", 5, 500, 3, 300)
    out = capsys.readouterr().out
    assert "[sim]" in out


# ---------------------------------------------------------------------------
# task_body
# ---------------------------------------------------------------------------


def test_task_body_with_description():
    subtask = Subtask(task_id="1", title="X", description="Do X")
    body = task_body(subtask)
    assert "Do X" in body


def test_task_body_with_deps():
    subtask = Subtask(task_id="2", title="X", description="Do Y", blocked_by={"1", "3"})
    body = task_body(subtask)
    assert "1, 3" in body


def test_task_body_no_description():
    subtask = Subtask(task_id="1", title="X", description="")
    body = task_body(subtask)
    assert body == ""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _minimal_task_list(**overrides: object) -> SubtaskList:
    defaults: dict = {
        "title": "My Plan",
        "description": "Goal.",
        "tasks": {
            "1": Subtask(task_id="1", title="Task A", description="Do A"),
        },
    }
    defaults.update(overrides)
    return SubtaskList(**defaults)


def test_validate_passes_on_valid_input():
    validate(_minimal_task_list())


def test_validate_raises_on_empty_tasks():
    with pytest.raises(ValueError, match="tasks"):
        validate(_minimal_task_list(tasks={}))


def test_validate_raises_on_unknown_dependency():
    tasks = {
        "1": Subtask(task_id="1", title="A", description="Do A", blocked_by={"99"}),
    }
    with pytest.raises(ValueError, match="unknown dependency"):
        validate(_minimal_task_list(tasks=tasks))


# ---------------------------------------------------------------------------
# run_sync — sim mode integration
# ---------------------------------------------------------------------------


def _minimal_plan(*, with_deps: bool = False) -> SubtaskList:
    tasks = {
        "1": Subtask(task_id="1", title="Task A", description="Do A."),
    }
    if with_deps:
        tasks["2"] = Subtask(task_id="2", title="Task B", description="Do B.", blocked_by={"1"})
    return SubtaskList(title="My Plan", description="Goal.", tasks=tasks)


def test_run_sync_sim_mode_succeeds(monkeypatch, capsys):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        code = run_sync(_minimal_plan(), "owner/repo")
    assert code == 0
    out = capsys.readouterr().out
    assert "[sim]" in out


def test_run_sync_sim_mode_with_dependencies(monkeypatch, capsys):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        code = run_sync(_minimal_plan(with_deps=True), "owner/repo")
    assert code == 0
    out = capsys.readouterr().out
    assert "blocked" in out.lower() or "blocked-by" in out.lower()


@patch("shipyard.commands.sync.create_issue", side_effect=RuntimeError("API down"))
def test_run_sync_parent_creation_failure_returns_1(mock_create, capsys):
    code = run_sync(_minimal_plan(), "owner/repo")
    assert code == 1


@patch("shipyard.commands.sync.create_issue")
@patch("shipyard.commands.sync.push")
@patch("shipyard.commands.sync.checkout_new_branch")
def test_run_sync_task_creation_failure(mock_checkout, mock_push, mock_create, capsys):
    mock_create.side_effect = [
        IssueRef(number=10, url="https://github.com/o/r/issues/10", database_id=1000),
        RuntimeError("API error"),
    ]
    code = run_sync(_minimal_plan(), "owner/repo")
    assert code == 1
    assert "FAILED" in capsys.readouterr().out


@patch("shipyard.commands.sync.create_issue")
@patch("shipyard.commands.sync.add_sub_issue")
@patch("shipyard.commands.sync.push")
@patch("shipyard.commands.sync.checkout_new_branch")
def test_run_sync_sub_issue_link_failure(mock_checkout, mock_push, mock_sub, mock_create, capsys):
    mock_create.side_effect = [
        IssueRef(number=10, url="https://github.com/o/r/issues/10", database_id=1000),
        IssueRef(number=11, url="https://github.com/o/r/issues/11", database_id=1100),
    ]
    mock_sub.side_effect = RuntimeError("link error")
    code = run_sync(_minimal_plan(), "owner/repo")
    assert code == 1
    assert "FAILED" in capsys.readouterr().out


@patch("shipyard.commands.sync.create_issue")
@patch("shipyard.commands.sync.add_sub_issue")
@patch("shipyard.commands.sync.add_blocked_by")
@patch("shipyard.commands.sync.push")
@patch("shipyard.commands.sync.checkout_new_branch")
def test_run_sync_skips_dep_when_task_missing(
    mock_checkout, mock_push, mock_blocked, mock_sub, mock_create
):
    mock_create.side_effect = [
        IssueRef(number=10, url="https://github.com/o/r/issues/10", database_id=1000),
        RuntimeError("API error for T1"),
        IssueRef(number=12, url="https://github.com/o/r/issues/12", database_id=1200),
    ]
    run_sync(_minimal_plan(with_deps=True), "owner/repo")
    mock_blocked.assert_not_called()


@patch("shipyard.commands.sync.create_issue")
@patch("shipyard.commands.sync.add_sub_issue")
@patch("shipyard.commands.sync.add_blocked_by")
@patch("shipyard.commands.sync.push")
@patch("shipyard.commands.sync.checkout_new_branch")
def test_run_sync_blocked_by_failure(
    mock_checkout, mock_push, mock_blocked, mock_sub, mock_create, capsys
):
    mock_create.side_effect = [
        IssueRef(number=10, url="https://github.com/o/r/issues/10", database_id=1000),
        IssueRef(number=11, url="https://github.com/o/r/issues/11", database_id=1100),
        IssueRef(number=12, url="https://github.com/o/r/issues/12", database_id=1200),
    ]
    mock_blocked.side_effect = RuntimeError("deps API down")
    code = run_sync(_minimal_plan(with_deps=True), "owner/repo")
    assert code == 1
    assert "FAILED" in capsys.readouterr().out


@patch("shipyard.commands.sync.create_issue")
@patch("shipyard.commands.sync.add_sub_issue")
@patch("shipyard.commands.sync.push")
@patch("shipyard.commands.sync.checkout_new_branch")
def test_run_sync_epic_branch_push_failure(mock_checkout, mock_push, mock_sub, mock_create, capsys):
    mock_create.side_effect = [
        IssueRef(number=10, url="https://github.com/o/r/issues/10", database_id=1000),
        IssueRef(number=11, url="https://github.com/o/r/issues/11", database_id=1100),
    ]
    mock_push.side_effect = RuntimeError("auth failed")
    code = run_sync(_minimal_plan(), "owner/repo")
    assert code == 1
    out = capsys.readouterr().out
    assert "epic branch" in out.lower() or "auth failed" in out


# ---------------------------------------------------------------------------
# sync CLI command
# ---------------------------------------------------------------------------


def _minimal_plan_json(*, with_deps: bool = False) -> str:
    tasks = {
        "1": {"task_id": "1", "title": "Task A", "description": "Do A.", "blocked_by": []},
    }
    if with_deps:
        tasks["2"] = {
            "task_id": "2",
            "title": "Task B",
            "description": "Do B.",
            "blocked_by": ["1"],
        }
    return json.dumps({"title": "My Plan", "description": "Goal.", "tasks": tasks})


def test_sync_cli_sim_mode_from_stdin(monkeypatch):
    from shipyard.commands.sync import sync

    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    runner = CliRunner()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = runner.invoke(sync, ["--repo", "owner/repo"], input=_minimal_plan_json())
    assert result.exit_code == 0


def test_sync_cli_invalid_json_raises():
    from shipyard.commands.sync import sync

    runner = CliRunner()
    result = runner.invoke(sync, [], input="not json")
    assert result.exit_code != 0


def test_sync_cli_validation_error_shown():
    from shipyard.commands.sync import sync

    data = json.dumps({"title": "T", "description": "D", "tasks": {}})
    runner = CliRunner()
    result = runner.invoke(sync, [], input=data)
    assert result.exit_code != 0
    assert "tasks" in result.output


def test_sync_cli_file_input(monkeypatch, tmp_path):
    from shipyard.commands.sync import sync

    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    f = tmp_path / "tasks.json"
    f.write_text(_minimal_plan_json())
    runner = CliRunner()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="existing-label\n", stderr="")
        result = runner.invoke(sync, ["--repo", "owner/repo", "--input", str(f)])
    assert result.exit_code == 0
