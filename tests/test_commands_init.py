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
