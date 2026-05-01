import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
TEMPLATES_DIR = REPO_ROOT / "shipyard" / "data" / "templates"
EVENTS_DIR = REPO_ROOT / ".github" / "tests" / "events"
DOCKER_CONTEXT = Path(__file__).parent  # docker build -t shipyard-act:latest tests/workflows/


def _act_available() -> bool:
    gh_ok = subprocess.run(["gh", "act", "--version"], capture_output=True).returncode == 0
    docker_ok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    return gh_ok and docker_ok


requires_act = pytest.mark.skipif(not _act_available(), reason="requires gh act + Docker")


@pytest.fixture
def substituted_template(tmp_path):
    """Factory: substituted_template('epic-driver.yml') → Path to tmp file with SHIPYARD_VERSION → 'main'."""

    def _make(name: str) -> Path:
        src = TEMPLATES_DIR / name
        dst = tmp_path / name
        dst.write_text(src.read_text().replace("SHIPYARD_VERSION", "main"))
        return dst

    return _make


def run_act(
    event: str,
    workflow: Path,
    event_payload: Path | None = None,
    inputs: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run gh act from REPO_ROOT so .actrc is picked up automatically."""
    cmd = ["gh", "act", event, "-W", str(workflow)]
    if event_payload:
        cmd += ["-e", str(event_payload)]
    for k, v in (inputs or {}).items():
        cmd += ["--input", f"{k}={v}"]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
