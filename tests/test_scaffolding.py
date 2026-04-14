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
