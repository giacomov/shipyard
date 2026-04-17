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


def test_sync_dry_run_reads_stdin():
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input=json.dumps(SAMPLE_DATA))
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_sync_exits_nonzero_on_invalid_json():
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input='{"title": "x"}')
    assert result.exit_code != 0


def test_sync_no_in_progress_label_skips_label_call():
    runner = CliRunner()
    with patch("shipyard.commands.sync.add_in_progress_label") as mock_label:
        result = runner.invoke(
            sync, ["--dry-run", "--no-in-progress-label"], input=json.dumps(SAMPLE_DATA)
        )
    assert result.exit_code == 0
    mock_label.assert_not_called()


def test_sync_default_adds_in_progress_label():
    runner = CliRunner()
    with patch("shipyard.commands.sync.add_in_progress_label") as mock_label:
        result = runner.invoke(sync, ["--dry-run"], input=json.dumps(SAMPLE_DATA))
    assert result.exit_code == 0
    mock_label.assert_called_once()
