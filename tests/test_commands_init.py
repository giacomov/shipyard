import yaml
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


def test_init_template_is_valid_yaml(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    workflow = tmp_path / ".github" / "workflows" / "epic-driver.yml"
    data = yaml.safe_load(workflow.read_text())
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_init_template_has_required_content(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content
    assert "@anthropic-ai/claude-code" in content
    assert "shipyard find-work" in content
    assert "shipyard execute" in content


def test_init_pins_version_in_workflow(tmp_path):
    runner = CliRunner()
    runner.invoke(init, [str(tmp_path)])
    content = (tmp_path / ".github" / "workflows" / "epic-driver.yml").read_text()
    assert "SHIPYARD_VERSION" not in content
    assert "shipyard==" in content
