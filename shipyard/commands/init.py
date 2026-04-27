"""shipyard init — set up the Shipyard workflow in a repository."""

import importlib.metadata
import subprocess
from importlib.resources import files as _res_files
from pathlib import Path

import click

_TEMPLATES = _res_files("shipyard.data.templates")
_SKILLS = _res_files("shipyard.data.skills")

_SKILL_NAMES = [
    "shipyard-system-prompt",
    "shipyard-implementer",
    "shipyard-spec-reviewer",
    "shipyard-code-quality-reviewer",
    "shipyard-doc-agent",
    "shipyard-doc-verifier",
    "shipyard-planner",
    "shipyard-replanner",
]


def _repo_root(path: str) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return Path(path)


def _install_skills(repo_root: Path, force: bool) -> None:
    for name in _SKILL_NAMES:
        dest_dir = repo_root / ".agents" / "skills" / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "SKILL.md"
        if dest.exists() and not force:
            click.echo(f"  Skipping {dest} (already exists, use --force to overwrite)")
            continue
        dest.write_text(_SKILLS.joinpath(name).joinpath("SKILL.md").read_text())
        click.echo(f"  Created {dest}")


@click.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing workflow file")
@click.option(
    "--skip-plan-driver", is_flag=True, default=False, help="Skip installing plan-driver.yml"
)
@click.option(
    "--from-main",
    is_flag=True,
    default=False,
    help="Install shipyard from HEAD of main instead of pinned version",
)
def init(path: str, force: bool, skip_plan_driver: bool, from_main: bool) -> None:
    """Set up the Shipyard epic-driver workflow in a repository.

    PATH defaults to the current directory.
    """
    workflows_dir = Path(path) / ".github" / "workflows"
    epic_dest = workflows_dir / "epic-driver.yml"
    plan_dest = workflows_dir / "plan-driver.yml"
    sync_dest = workflows_dir / "sync-driver.yml"

    if epic_dest.exists() and not force:
        raise click.ClickException(f"{epic_dest} already exists. Use --force to overwrite.")

    if not skip_plan_driver and plan_dest.exists() and not force:
        raise click.ClickException(f"{plan_dest} already exists. Use --force to overwrite.")

    if not skip_plan_driver and sync_dest.exists() and not force:
        raise click.ClickException(f"{sync_dest} already exists. Use --force to overwrite.")

    if from_main:
        install_ref = "main"
    else:
        try:
            install_ref = importlib.metadata.version("shipyard")
        except importlib.metadata.PackageNotFoundError:
            install_ref = "0.1.0"

    epic_content = (
        (_TEMPLATES / "epic-driver.yml")
        .read_text(encoding="utf-8")
        .replace("SHIPYARD_VERSION", install_ref)
    )

    epic_dest.parent.mkdir(parents=True, exist_ok=True)
    epic_dest.write_text(epic_content)
    click.echo(f"Created {epic_dest}")

    if not skip_plan_driver:
        plan_content = (
            (_TEMPLATES / "plan-driver.yml")
            .read_text(encoding="utf-8")
            .replace("SHIPYARD_VERSION", install_ref)
        )
        plan_dest.write_text(plan_content)
        click.echo(f"Created {plan_dest}")

        sync_content = (
            (_TEMPLATES / "sync-driver.yml")
            .read_text(encoding="utf-8")
            .replace("SHIPYARD_VERSION", install_ref)
        )
        sync_dest.write_text(sync_content)
        click.echo(f"Created {sync_dest}")

    click.echo("\nInstalling agent skills...")
    _install_skills(_repo_root(path), force)
    click.echo("  Tip: edit .agents/skills/shipyard-*/SKILL.md to customize agent behavior.")

    click.echo(
        "\nNext step: add CLAUDE_CODE_OAUTH_TOKEN as a secret in your GitHub repository settings."
    )
