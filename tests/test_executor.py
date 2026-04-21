import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from shipyard.schemas import Subtask, SubtaskList
from shipyard.utils.gh import close_issues_body


def _task(**kwargs) -> Subtask:
    defaults = dict(task_id="5", title="Do X", description="spec")
    return Subtask(**{**defaults, **kwargs})


def _work(**kwargs) -> SubtaskList:
    tasks = kwargs.pop("tasks", None)
    defaults: dict = dict(epic_id="10", title="Epic", description="")
    if tasks is not None:
        defaults["tasks"] = {t.task_id: t for t in tasks}
    defaults.update(kwargs)
    return SubtaskList(**defaults)


# ---------------------------------------------------------------------------
# close_issues_body
# ---------------------------------------------------------------------------


def test_close_issues_body():
    body = close_issues_body([5, 12, 99])
    assert "Closes #5" in body
    assert "Closes #12" in body
    assert "Closes #99" in body


def test_close_issues_body_single():
    body = close_issues_body([1])
    assert "Closes #1" in body


# ---------------------------------------------------------------------------
# run_all_issues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_issue_pipeline", new_callable=AsyncMock, return_value=True)
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_calls_pipeline_for_each_task(mock_sha, mock_pipeline):
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id="1", title="A"), _task(task_id="2", title="B")]
    work = _work(tasks=tasks)
    results = await run_all_issues(work, model="sonnet", effort="high")
    assert mock_pipeline.call_count == 2
    assert results == {"successful": ["1", "2"], "failed": []}


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_issue_pipeline", new_callable=AsyncMock, return_value=True)
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_calls_pipeline_for_all_tasks(mock_sha, mock_pipeline):
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id=str(i), title=f"T{i}") for i in range(3)]
    work = _work(tasks=tasks)
    results = await run_all_issues(work, model="sonnet", effort="high")
    assert mock_pipeline.call_count == 3
    assert results == {"successful": ["0", "1", "2"], "failed": []}


@pytest.mark.asyncio
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_tracks_failures(mock_sha):
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id=str(i), title=f"T{i}") for i in range(3)]
    work = _work(tasks=tasks)

    with patch(
        "shipyard.commands.execute.run_issue_pipeline",
        new_callable=AsyncMock,
        side_effect=[True, False, True],
    ):
        results = await run_all_issues(work, model="sonnet", effort="high")

    assert results == {"successful": ["0", "2"], "failed": ["1"]}


@pytest.mark.asyncio
@patch(
    "shipyard.commands.execute.run_issue_pipeline",
    new_callable=AsyncMock,
    return_value=False,
)
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_all_fail(mock_sha, mock_pipeline):
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id="1", title="A"), _task(task_id="2", title="B")]
    work = _work(tasks=tasks)
    results = await run_all_issues(work, model="sonnet", effort="high")
    assert results == {"successful": [], "failed": ["1", "2"]}


# ---------------------------------------------------------------------------
# execute command
# ---------------------------------------------------------------------------


def test_execute_command_missing_input_file():
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    runner = CliRunner()
    result = runner.invoke(execute)
    assert result.exit_code != 0
    assert "provide -i" in result.output.lower() or "required" in result.output.lower()


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


@patch("shipyard.commands.execute.resolve_repo", return_value="owner/repo")
@patch(
    "shipyard.commands.execute.run_all_issues",
    new_callable=AsyncMock,
    return_value={"successful": ["5", "6"], "failed": []},
)
def test_execute_writes_results_file(mock_run, mock_repo, tmp_path: Any):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    work_file = _write_work(tmp_path)
    results_path = tmp_path / "shipyard-results.json"

    runner = CliRunner()
    with patch("shipyard.commands.execute.settings") as mock_settings:
        mock_settings.results_file = str(results_path)
        result = runner.invoke(execute, ["-i", work_file])

    assert result.exit_code == 0
    assert results_path.exists()
    data = json.loads(results_path.read_text())
    assert data == {"successful": ["5", "6"], "failed": []}


@patch("shipyard.commands.execute.resolve_repo", return_value="owner/repo")
@patch(
    "shipyard.commands.execute.run_all_issues",
    new_callable=AsyncMock,
    return_value={"successful": [], "failed": ["5", "6"]},
)
def test_execute_exits_nonzero_on_failure(mock_run, mock_repo, tmp_path: Any):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    work_file = _write_work(tmp_path)
    results_path = tmp_path / "shipyard-results.json"

    runner = CliRunner()
    with patch("shipyard.commands.execute.settings") as mock_settings:
        mock_settings.results_file = str(results_path)
        result = runner.invoke(execute, ["-i", work_file])

    assert result.exit_code == 1
    assert results_path.exists()
    data = json.loads(results_path.read_text())
    assert data == {"successful": [], "failed": ["5", "6"]}
