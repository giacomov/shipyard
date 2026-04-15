import importlib
from pathlib import Path


def test_shipyard_package_importable():
    mod = importlib.import_module("shipyard")
    assert mod is not None


def test_shipyard_commands_package_importable():
    mod = importlib.import_module("shipyard.commands")
    assert mod is not None


def test_required_files_exist():
    root = Path(__file__).parent.parent
    assert (root / "pyproject.toml").exists()
    assert (root / "requirements.txt").exists()
    assert (root / "tests" / "fixtures").is_dir()


def test_cli_entry_point_lists_all_commands():
    from click.testing import CliRunner

    from shipyard.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "tasks" in result.output
    assert "sync" in result.output
    assert "init" in result.output
    assert "find-work" in result.output
    assert "execute" in result.output
