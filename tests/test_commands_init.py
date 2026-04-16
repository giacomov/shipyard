import importlib.metadata
from pathlib import Path

from click.testing import CliRunner

from shipyard.commands.init import init


def test_init_creates_workflow_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    assert workflow.exists()


def test_init_fails_if_file_already_exists(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code != 0
    assert workflow.read_text() == "existing content"


def test_init_force_overwrites_existing_file(tmp_path):
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path), "--force"])
    assert result.exit_code == 0
    assert workflow.read_text() != "existing content"


def test_init_pins_version_in_workflow(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    assert "SHIPYARD_VERSION" not in content
    assert "giacomov/shipyard@v" in content


def test_init_creates_both_workflow_files(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    workflows_dir = tmp_path / ".github" / "workflows"
    assert (workflows_dir / "epic-driver.yml").exists()
    assert (workflows_dir / "plan-driver.yml").exists()


def test_init_skip_plan_driver(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path), "--skip-plan-driver"])
    assert result.exit_code == 0, result.output
    workflows_dir = tmp_path / ".github" / "workflows"
    assert (workflows_dir / "epic-driver.yml").exists()
    assert not (workflows_dir / "plan-driver.yml").exists()


def test_init_fails_if_plan_driver_already_exists(tmp_path: Path) -> None:
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    plan_dest = workflows_dir / "plan-driver.yml"
    plan_dest.write_text("existing plan content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path)])
    assert result.exit_code != 0
    assert plan_dest.read_text() == "existing plan content"


def test_init_force_overwrites_plan_driver(tmp_path: Path) -> None:
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    plan_dest = workflows_dir / "plan-driver.yml"
    plan_dest.write_text("dummy content")
    runner = CliRunner()
    result = runner.invoke(init, [str(tmp_path), "--force"])
    assert result.exit_code == 0, result.output
    assert plan_dest.read_text() != "dummy content"


def test_init_pins_version_in_plan_driver(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "plan-driver.yml").read_text()
    version = importlib.metadata.version("shipyard")
    assert "SHIPYARD_VERSION" not in content
    assert version in content
