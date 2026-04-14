import yaml
from pathlib import Path


def test_epic_driver_workflow_valid_yaml():
    path = Path(".github/workflows/epic-driver.yml")
    assert path.exists(), "Workflow file missing"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_execute_job_has_claude_oauth_token():
    path = Path(".github/workflows/epic-driver.yml")
    content = path.read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content


def test_execute_job_installs_claude_code_cli():
    path = Path(".github/workflows/epic-driver.yml")
    content = path.read_text()
    assert "@anthropic-ai/claude-code" in content
