import importlib
from pathlib import Path


def test_scripts_package_importable():
    mod = importlib.import_module("scripts")
    assert mod is not None


def test_required_files_exist():
    root = Path(__file__).parent.parent
    assert (root / "pyproject.toml").exists()
    assert (root / "requirements.txt").exists()
    assert (root / "prompts").is_dir()
    assert (root / "tests" / "fixtures").is_dir()
