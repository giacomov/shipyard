import json
import os
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


@patch(
    "shipyard.commands.execute.run_all_issues",
    new_callable=AsyncMock,
    return_value={"successful": ["5", "6"], "failed": []},
)
def test_execute_writes_results_file(mock_run, tmp_path: Any):
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


@patch(
    "shipyard.commands.execute.run_all_issues",
    new_callable=AsyncMock,
    return_value={"successful": [], "failed": ["5", "6"]},
)
def test_execute_exits_nonzero_on_failure(mock_run, tmp_path: Any):
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


# ---------------------------------------------------------------------------
# run_issue_pipeline — exception / reset path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_issue_pipeline_inner_sim_mode():
    from shipyard.commands.execute import _run_issue_pipeline_inner

    task = _task(task_id="1", title="Do something important")
    work = _work(tasks=[task])

    with patch.dict(os.environ, {"SHIPYARD_SIM_MODE": "1"}):
        result = await _run_issue_pipeline_inner(
            task, work, "abc123", model="sonnet", effort="high"
        )

    assert result is True


@pytest.mark.asyncio
async def test_pipeline_inner_sends_five_queries_in_order():
    from shipyard.commands.execute import _run_issue_pipeline_inner

    task = _task(task_id="5", title="Do something")
    work = _work(tasks=[task])

    mock_client = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("shipyard.commands.execute.get_sdk_client", return_value=mock_client),
        patch(
            "shipyard.commands.execute.receive_from_client", new_callable=AsyncMock, return_value=""
        ),
    ):
        result = await _run_issue_pipeline_inner(task, work, "abc", model="sonnet", effort="high")

    assert result is True
    assert mock_client.query.call_count == 5

    prompts = [call.args[0] for call in mock_client.query.call_args_list]
    assert "shipyard-implementer" in prompts[0]
    assert "[current task]" in prompts[0]
    assert "stage and commit" in prompts[1]
    assert "spec reviewer" in prompts[2]
    assert "git diff --stat abc..HEAD" in prompts[2]
    assert "code quality" in prompts[3]
    assert "git diff --stat abc..HEAD" in prompts[3]
    assert "tests" in prompts[4]


@pytest.mark.asyncio
@patch("shipyard.commands.execute.get_head_sha", return_value="abc")
async def test_run_all_issues_passes_correct_tasks(mock_sha):
    from shipyard.commands.execute import run_all_issues

    tasks = [_task(task_id="T1", title="Task 1"), _task(task_id="T2", title="Task 2")]
    work = _work(tasks=tasks)

    with patch(
        "shipyard.commands.execute.run_issue_pipeline",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_pipeline:
        results = await run_all_issues(work, model="sonnet", effort="high")

    assert mock_pipeline.call_count == 2
    assert mock_pipeline.call_args_list[0].args[0].task_id == "T1"
    assert mock_pipeline.call_args_list[1].args[0].task_id == "T2"
    assert results == {"successful": ["T1", "T2"], "failed": []}


@pytest.mark.asyncio
@patch(
    "shipyard.commands.execute._run_issue_pipeline_inner",
    new_callable=AsyncMock,
    side_effect=RuntimeError("agent blew up"),
)
async def test_run_issue_pipeline_calls_reset_on_exception(mock_inner):
    from shipyard.commands.execute import run_issue_pipeline

    reset_calls: list[str] = []
    task = _task(task_id="3", title="Boom")
    work = _work(tasks=[task])
    ok = await run_issue_pipeline(
        task,
        work,
        "deadbeef",
        reset_fn=lambda sha: reset_calls.append(sha),
        model="sonnet",
        effort="high",
    )

    assert ok is False
    assert reset_calls == ["deadbeef"]


@pytest.mark.asyncio
@patch(
    "shipyard.commands.execute._run_issue_pipeline_inner",
    new_callable=AsyncMock,
    side_effect=RuntimeError("agent blew up"),
)
async def test_run_issue_pipeline_reset_exception_is_swallowed(mock_inner):
    from shipyard.commands.execute import run_issue_pipeline

    def bad_reset(sha: str) -> None:
        raise OSError("git broken")

    task = _task(task_id="3", title="Boom")
    work = _work(tasks=[task])
    ok = await run_issue_pipeline(
        task, work, "deadbeef", reset_fn=bad_reset, model="sonnet", effort="high"
    )

    assert ok is False


# ---------------------------------------------------------------------------
# execute CLI — revision mode validation
# ---------------------------------------------------------------------------


def test_execute_revision_mode_conflict_with_input(tmp_path: Any):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    work_file = _write_work(tmp_path)
    review_file = tmp_path / "review.txt"
    review_file.write_text("feedback")
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("context")

    runner = CliRunner()
    result = runner.invoke(
        execute,
        [
            "-i",
            work_file,
            "--review-feedback-file",
            str(review_file),
            "--prompt-file",
            str(prompt_file),
        ],
    )
    assert result.exit_code != 0


def test_execute_revision_mode_missing_prompt_file(tmp_path: Any):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    review_file = tmp_path / "review.txt"
    review_file.write_text("feedback")

    runner = CliRunner()
    result = runner.invoke(execute, ["--review-feedback-file", str(review_file)])
    assert result.exit_code != 0


@patch(
    "shipyard.commands.execute.run_all_issues",
    new_callable=AsyncMock,
    return_value={"successful": ["revision"], "failed": []},
)
def test_execute_revision_mode_success(mock_run, tmp_path: Any):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    review_file = tmp_path / "review.txt"
    review_file.write_text("Please rename the variable")
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Issue #5: Do stuff\n\nDetails")

    runner = CliRunner()
    with patch("shipyard.commands.execute.settings") as mock_settings:
        mock_settings.revision_model = "sonnet"
        mock_settings.revision_effort = "high"
        result = runner.invoke(
            execute,
            ["--review-feedback-file", str(review_file), "--prompt-file", str(prompt_file)],
        )

    assert result.exit_code == 0
    call_kwargs = mock_run.call_args
    work_arg = call_kwargs.args[0]
    assert "revision" in work_arg.tasks
    assert "Please rename the variable" in work_arg.tasks["revision"].description
    assert "Do stuff" in work_arg.tasks["revision"].description


@patch(
    "shipyard.commands.execute.run_all_issues",
    new_callable=AsyncMock,
    return_value={"successful": [], "failed": ["revision"]},
)
def test_execute_revision_mode_failure_exits_nonzero(mock_run, tmp_path: Any):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    review_file = tmp_path / "review.txt"
    review_file.write_text("fix this")
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("context")

    runner = CliRunner()
    with patch("shipyard.commands.execute.settings") as mock_settings:
        mock_settings.revision_model = "sonnet"
        mock_settings.revision_effort = "high"
        result = runner.invoke(
            execute,
            ["--review-feedback-file", str(review_file), "--prompt-file", str(prompt_file)],
        )

    assert result.exit_code == 1
