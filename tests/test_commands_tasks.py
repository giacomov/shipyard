import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from shipyard.commands.tasks import tasks
from shipyard.schemas import Subtask, SubtaskList


async def _fake_run_task_agent(prompt: str, cwd: str, task_list: SubtaskList) -> None:
    task_list.tasks["1"] = Subtask(task_id="1", title="Alpha", description="Do alpha.")
    task_list.tasks["2"] = Subtask(
        task_id="2", title="Beta", description="Do beta.", blocked_by={"1"}
    )


async def _fake_run_task_agent_empty(prompt: str, cwd: str, task_list: SubtaskList) -> None:
    pass


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
