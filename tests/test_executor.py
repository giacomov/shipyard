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
@patch("shipyard.commands.execute.run_issue_pipeline", new_callable=AsyncMock)
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_returns_results_dict(mock_sha, mock_pipeline):
    mock_pipeline.side_effect = [True, False]
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id="1", title="A"), _task(task_id="2", title="B")]
    work = _work(tasks=tasks)
    results = await run_all_issues(work)
    assert results == {"1": True, "2": False}


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_issue_pipeline", new_callable=AsyncMock, return_value=True)
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_all_success(mock_sha, mock_pipeline):
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id=str(i), title=f"T{i}") for i in range(3)]
    work = _work(tasks=tasks)
    results = await run_all_issues(work)
    assert all(results.values())
    assert len(results) == 3


# ---------------------------------------------------------------------------
# execute command — env var guards
# ---------------------------------------------------------------------------


def test_execute_command_missing_input_file():
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    runner = CliRunner()
    result = runner.invoke(execute)
    assert result.exit_code != 0
    assert "input" in result.output.lower() or "required" in result.output.lower()
