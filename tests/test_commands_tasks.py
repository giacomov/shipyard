import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from shipyard.commands.tasks import (
    _run_task_agent,
    _tool_commit,
    _tool_create_task,
    _tool_delete_task,
    _tool_link_tasks,
    _tool_unlink_tasks,
    tasks,
)
from shipyard.schemas import Subtask, SubtaskList


async def _fake_run_task_agent(prompt: str, cwd: str, task_list: SubtaskList) -> None:
    task_list.tasks["1"] = Subtask(task_id="1", title="Alpha", description="Do alpha.")
    task_list.tasks["2"] = Subtask(
        task_id="2", title="Beta", description="Do beta.", blocked_by={"1"}
    )


def test_tasks_reads_file_and_outputs_json(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# My Plan\n\nSome plan content.\n")
    out_file = tmp_path / "tasks.json"

    with patch("shipyard.commands.tasks._run_task_agent", new=_fake_run_task_agent):
        result = runner.invoke(
            tasks, ["-i", str(plan_file), "-o", str(out_file), "--title", "My Epic"]
        )

    assert result.exit_code == 0, result.output
    data = json.loads(out_file.read_text())
    assert data["title"] == "My Epic"
    assert data["description"] == "# My Plan\n\nSome plan content.\n"
    assert "1" in data["tasks"]
    assert data["tasks"]["1"]["title"] == "Alpha"
    assert data["tasks"]["1"]["blocked_by"] == []
    assert sorted(data["tasks"]["2"]["blocked_by"]) == ["1"]


def test_tasks_writes_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")
    out = tmp_path / "out.json"

    with patch("shipyard.commands.tasks._run_task_agent", new=_fake_run_task_agent):
        result = runner.invoke(tasks, ["-i", str(plan_file), "-o", str(out), "--title", "Epic"])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert "tasks" in data


def test_tasks_output_excludes_internal_fields(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")
    out = tmp_path / "out.json"

    with patch("shipyard.commands.tasks._run_task_agent", new=_fake_run_task_agent):
        result = runner.invoke(tasks, ["-i", str(plan_file), "-o", str(out), "--title", "Epic"])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert "committed" not in data
    assert "drafting" not in data


def test_tasks_requires_title(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")

    result = runner.invoke(tasks, ["-i", str(plan_file)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# _run_task_agent — sim mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_task_agent_sim_mode() -> None:
    task_list = SubtaskList(title="Test Epic", description="A plan")
    with patch.dict(os.environ, {"SHIPYARD_SIM_MODE": "1"}):
        await _run_task_agent("Use the shipyard-task-agent skill.", cwd=".", task_list=task_list)
    # SimSDKClient is a no-op — queries don't produce tasks or commit


# ---------------------------------------------------------------------------
# _tool_create_task
# ---------------------------------------------------------------------------


def _make_task_list(*task_ids: str) -> SubtaskList:
    tl = SubtaskList(title="T", description="d")
    for tid in task_ids:
        tl.tasks[tid] = Subtask(task_id=tid, title=f"Task {tid}", description=f"Desc {tid}")
    return tl


@pytest.mark.asyncio
async def test_tool_create_task_valid() -> None:
    tl = _make_task_list()
    result = await _tool_create_task(
        {"task_id": "T1", "title": "My Task", "description": "Do stuff"}, tl
    )
    assert result["success"] is True
    assert "T1" in tl.tasks
    assert tl.tasks["T1"].title == "My Task"
    assert tl.drafting is True


@pytest.mark.asyncio
async def test_tool_create_task_missing_title() -> None:
    tl = _make_task_list()
    result = await _tool_create_task({"task_id": "T1", "description": "Do stuff"}, tl)
    assert "error" in result
    assert tl.drafting is True


@pytest.mark.asyncio
async def test_tool_create_task_missing_task_id() -> None:
    tl = _make_task_list()
    result = await _tool_create_task({"title": "X", "description": "Y"}, tl)
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_create_task_missing_description() -> None:
    tl = _make_task_list()
    result = await _tool_create_task({"task_id": "T1", "title": "X"}, tl)
    assert "error" in result


# ---------------------------------------------------------------------------
# _tool_delete_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_delete_task_valid() -> None:
    tl = _make_task_list("T1", "T2")
    tl.tasks["T2"].blocked_by.add("T1")
    result = await _tool_delete_task({"task_id": "T1"}, tl)
    assert result["success"] is True
    assert "T1" not in tl.tasks
    assert "T1" not in tl.tasks["T2"].blocked_by


@pytest.mark.asyncio
async def test_tool_delete_task_missing_task_id() -> None:
    tl = _make_task_list("T1")
    result = await _tool_delete_task({}, tl)
    assert "error" in result
    assert "T1" in tl.tasks


@pytest.mark.asyncio
async def test_tool_delete_task_not_found() -> None:
    tl = _make_task_list("T1")
    result = await _tool_delete_task({"task_id": "T99"}, tl)
    assert "error" in result
    assert "T1" in tl.tasks


# ---------------------------------------------------------------------------
# _tool_link_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_link_tasks_valid() -> None:
    tl = _make_task_list("T1", "T2")
    result = await _tool_link_tasks({"task_id": "T2", "add_blocked_by": ["T1"]}, tl)
    assert result["success"] is True
    assert "T1" in tl.tasks["T2"].blocked_by


@pytest.mark.asyncio
async def test_tool_link_tasks_task_not_found() -> None:
    tl = _make_task_list("T1")
    result = await _tool_link_tasks({"task_id": "T99", "add_blocked_by": ["T1"]}, tl)
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_link_tasks_empty_blocked_by() -> None:
    tl = _make_task_list("T1")
    result = await _tool_link_tasks({"task_id": "T1", "add_blocked_by": []}, tl)
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_link_tasks_dep_not_found() -> None:
    tl = _make_task_list("T1")
    result = await _tool_link_tasks({"task_id": "T1", "add_blocked_by": ["T99"]}, tl)
    assert "error" in result
    assert "T99" not in tl.tasks["T1"].blocked_by


# ---------------------------------------------------------------------------
# _tool_unlink_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_unlink_tasks_valid() -> None:
    tl = _make_task_list("T1", "T2")
    tl.tasks["T2"].blocked_by.add("T1")
    result = await _tool_unlink_tasks({"task_id": "T2", "remove_blocked_by": ["T1"]}, tl)
    assert result["success"] is True
    assert "T1" not in tl.tasks["T2"].blocked_by


@pytest.mark.asyncio
async def test_tool_unlink_tasks_task_not_found() -> None:
    tl = _make_task_list("T1")
    result = await _tool_unlink_tasks({"task_id": "T99", "remove_blocked_by": ["T1"]}, tl)
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_unlink_tasks_empty_remove_list() -> None:
    tl = _make_task_list("T1")
    result = await _tool_unlink_tasks({"task_id": "T1", "remove_blocked_by": []}, tl)
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_unlink_tasks_dep_not_found() -> None:
    tl = _make_task_list("T1")
    result = await _tool_unlink_tasks({"task_id": "T1", "remove_blocked_by": ["T99"]}, tl)
    assert "error" in result


# ---------------------------------------------------------------------------
# _tool_commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_commit() -> None:
    tl = _make_task_list()
    tl.committed = False
    result = await _tool_commit({}, tl)
    assert result["success"] is True
    assert tl.committed is True
