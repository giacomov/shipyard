from pathlib import Path

import yaml

# ── Dogfood workflow (this repo's own .github/workflows/epic-driver.yml) ──


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


# ── Bundled template (shipped inside the package) ──


def test_template_workflow_valid_yaml():
    path = Path("shipyard/templates/epic-driver.yml")
    assert path.exists(), "Bundled template missing"
    with open(path) as f:
        data = yaml.safe_load(f)
    assert "jobs" in data
    assert "find-work" in data["jobs"]
    assert "execute" in data["jobs"]
    assert data["jobs"]["execute"]["needs"] == "find-work"


def test_template_has_claude_oauth_token():
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "CLAUDE_CODE_OAUTH_TOKEN" in content


def test_template_installs_claude_code_cli():
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "@anthropic-ai/claude-code" in content


def test_template_uses_shipyard_cli_commands():
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "shipyard find-work" in content
    assert "shipyard execute" in content


def test_template_has_version_placeholder():
    """The raw template has SHIPYARD_VERSION; init replaces it at copy time."""
    path = Path("shipyard/templates/epic-driver.yml")
    content = path.read_text()
    assert "SHIPYARD_VERSION" in content
