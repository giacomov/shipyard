import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from shipyard.commands.tasks import tasks

FIXTURES = Path(__file__).parent / "fixtures"

_FAKE_TASKS = [
    {"id": "1", "subject": "Alpha", "description": "Do alpha.", "blockedBy": []},
    {"id": "2", "subject": "Beta", "description": "Do beta.", "blockedBy": ["1"]},
]


def test_tasks_reads_file_and_outputs_json(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# My Plan\n\nSome plan content.\n")

    with (
        patch("shipyard.commands.tasks.asyncio.run"),
        patch("shipyard.commands.tasks._load_task_files", return_value=_FAKE_TASKS),
    ):
        result = runner.invoke(tasks, ["-i", str(plan_file), "--title", "My Epic"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["title"] == "My Epic"
    assert data["body"] == ""
    assert len(data["tasks"]) == 2
    assert data["tasks"][0]["subject"] == "Alpha"
    assert data["tasks"][0]["status"] == "pending"
    assert data["tasks"][1]["dependencies"] == ["1"]


def test_tasks_writes_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")
    out = tmp_path / "out.json"

    with (
        patch("shipyard.commands.tasks.asyncio.run"),
        patch("shipyard.commands.tasks._load_task_files", return_value=_FAKE_TASKS),
    ):
        result = runner.invoke(tasks, ["-i", str(plan_file), "-o", str(out), "--title", "Epic"])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert "tasks" in data


def test_tasks_exits_nonzero_when_agent_creates_no_tasks(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")

    with (
        patch("shipyard.commands.tasks.asyncio.run"),
        patch("shipyard.commands.tasks._load_task_files", return_value=[]),
    ):
        result = runner.invoke(tasks, ["-i", str(plan_file), "--title", "Epic"])

    assert result.exit_code != 0


def test_tasks_exits_nonzero_on_bad_dependency(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")

    bad_tasks = [
        {"id": "1", "subject": "A", "description": "Desc.", "blockedBy": ["99"]},
    ]

    with (
        patch("shipyard.commands.tasks.asyncio.run"),
        patch("shipyard.commands.tasks._load_task_files", return_value=bad_tasks),
    ):
        result = runner.invoke(tasks, ["-i", str(plan_file), "--title", "Epic"])

    assert result.exit_code != 0


def test_tasks_requires_title(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")

    result = runner.invoke(tasks, ["-i", str(plan_file)])
    assert result.exit_code != 0


def test_tasks_sets_env_var_before_agent(tmp_path: Path) -> None:
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("# P\n\nDesc.\n")

    captured_env: list[str | None] = []

    def fake_run(coro):  # type: ignore[no-untyped-def]
        captured_env.append(os.environ.get("CLAUDE_CODE_TASK_LIST_ID"))

    import os

    with (
        patch("shipyard.commands.tasks.asyncio.run", side_effect=fake_run),
        patch("shipyard.commands.tasks._load_task_files", return_value=_FAKE_TASKS),
    ):
        runner.invoke(tasks, ["-i", str(plan_file), "--title", "Epic"])

    assert captured_env[0] is not None
