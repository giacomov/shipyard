import json
from pathlib import Path

from click.testing import CliRunner

from shipyard.commands.tasks import tasks

FIXTURES = Path(__file__).parent / "fixtures"


def test_tasks_reads_stdin_outputs_json():
    runner = CliRunner()
    plan_text = "# My Plan\n\n**Goal:** Do X.\n\n### Task 1: Alpha\n\n**Depends on:** (none)\n\nDo alpha.\n"
    result = runner.invoke(tasks, input=plan_text)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "My Plan"
    assert len(data["tasks"]) == 1


def test_tasks_reads_file_with_input_flag(tmp_path):
    runner = CliRunner()
    plan_file = tmp_path / "plan.md"
    plan_file.write_text(
        "# My Plan\n\n**Goal:** Do X.\n\n### Task 1: Alpha\n\n**Depends on:** (none)\n\nDo alpha.\n"
    )
    result = runner.invoke(tasks, ["-i", str(plan_file)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["title"] == "My Plan"


def test_tasks_writes_output_file(tmp_path):
    runner = CliRunner()
    plan_text = "# P\n\n**Goal:** X.\n\n### Task 1: A\n\n**Depends on:** (none)\n\nDesc.\n"
    out = tmp_path / "out.json"
    result = runner.invoke(tasks, ["-o", str(out)], input=plan_text)
    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert "tasks" in data


def test_tasks_exits_nonzero_on_bad_dependency():
    runner = CliRunner()
    plan_text = "# P\n\n**Goal:** X.\n\n### Task 1: A\n\n**Depends on:** Task 99\n\nDesc.\n"
    result = runner.invoke(tasks, input=plan_text)
    assert result.exit_code != 0
