import json

from click.testing import CliRunner

from shipyard.commands.sync import sync


def test_sync_dry_run_reads_stdin():
    runner = CliRunner()
    data = {
        "title": "My Epic",
        "body": "Goal.",
        "tasks": [{"id": "1", "subject": "Task A", "description": "Do A.", "status": "pending", "dependencies": []}],
    }
    result = runner.invoke(sync, ["--dry-run"], input=json.dumps(data))
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_sync_exits_nonzero_on_invalid_json():
    runner = CliRunner()
    result = runner.invoke(sync, ["--dry-run"], input='{"title": "x"}')
    assert result.exit_code != 0
