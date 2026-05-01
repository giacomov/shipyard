import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from shipyard.commands.update_docs import _run_update_docs, update_docs


@pytest.mark.asyncio
async def test_run_update_docs_sim_mode() -> None:
    with patch.dict(os.environ, {"SHIPYARD_SIM_MODE": "1"}):
        await _run_update_docs(base_sha="abc1234")


def test_update_docs_cli_sim_mode() -> None:
    runner = CliRunner()
    with patch.dict(os.environ, {"SHIPYARD_SIM_MODE": "1"}):
        result = runner.invoke(update_docs, ["--base-sha", "abc1234"])
    assert result.exit_code == 0, result.output
