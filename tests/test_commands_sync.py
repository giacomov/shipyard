import json
from unittest.mock import patch

from click.testing import CliRunner

from shipyard.commands.sync import sync

SAMPLE_DATA = {
    "title": "My Epic",
    "description": "Goal.",
    "tasks": {
        "1": {
            "task_id": "1",
            "title": "Task A",
            "description": "Do A.",
            "blocked_by": [],
        }
    },
}


def test_sync_sim_mode_reads_stdin(monkeypatch):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    runner = CliRunner()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        result = runner.invoke(sync, ["--repo", "owner/repo"], input=json.dumps(SAMPLE_DATA))
    assert result.exit_code == 0
    assert "[sim]" in result.output


def test_sync_exits_nonzero_on_invalid_json(monkeypatch):
    monkeypatch.setenv("SHIPYARD_SIM_MODE", "true")
    runner = CliRunner()
    result = runner.invoke(sync, [], input='{"title": "x"}')
    assert result.exit_code != 0
