"""shipyard init — set up the Shipyard workflow in a repository."""

import importlib.metadata
import subprocess
from importlib.resources import files as _res_files
from pathlib import Path

import click

_TEMPLATES = _res_files("shipyard.data.templates")
_SKILLS = _res_files("shipyard.data.skills")

_SKILL_NAMES = [
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
            click.echo(f"  {dest} (skipped, use --force to overwrite)")
            continue
        dest.write_text(_SKILLS.joinpath(name).joinpath("SKILL.md").read_text())
        click.echo(f"  {dest}")


@click.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing workflow file")
@click.option(
    "--skip-plan-driver", is_flag=True, default=False, help="Skip installing plan-driver.yml"
)
@click.option(
    "--dev",
    default=None,
    metavar="BRANCH",
    help="Install shipyard from this branch instead of the pinned version (e.g. --dev main)",
)
def init(path: str, force: bool, skip_plan_driver: bool, dev: str | None) -> None:
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

    if dev is not None:
        install_ref = dev
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

    click.echo("GitHub Actions workflows:")
    epic_dest.parent.mkdir(parents=True, exist_ok=True)
    epic_dest.write_text(epic_content)
    click.echo(f"  {epic_dest}")

    if not skip_plan_driver:
        plan_content = (
            (_TEMPLATES / "plan-driver.yml")
            .read_text(encoding="utf-8")
            .replace("SHIPYARD_VERSION", install_ref)
        )
        plan_dest.write_text(plan_content)
        click.echo(f"  {plan_dest}")

        sync_content = (
            (_TEMPLATES / "sync-driver.yml")
            .read_text(encoding="utf-8")
            .replace("SHIPYARD_VERSION", install_ref)
        )
        sync_dest.write_text(sync_content)
        click.echo(f"  {sync_dest}")

    click.echo("\nAgent skills:")
    _install_skills(_repo_root(path), force)

    click.echo(
        "\nNext steps:\n"
        "\n"
        "  1. Commit the workflows and skills:\n"
        "\n"
        "       git add .github .agents\n"
        "       git commit -m 'chore: add shipyard workflows and agent skills'\n"
        "\n"
        "  2. Make sure CLAUDE_CODE_OAUTH_TOKEN is set as a secret in your repository.\n"
        "     Settings -> Secrets and variables -> Actions -> New repository secret\n"
        "\n"
        "  3. (Claude Code users) From the root of the repo, link skills so Claude Code\n"
        "     can discover them:\n"
        "\n"
        "       mkdir -p .claude\n"
        "       ln -s .agents .claude/skills\n"
        "       git add .claude\n"
        "       git commit -m 'chore: link shipyard skills for Claude Code'\n"
        "\n"
        "  4. Allow Actions to create pull requests:\n"
        "     Settings -> Actions -> General -> Workflow permissions\n"
        "     -> Allow GitHub Actions to create and approve pull requests\n"
        "\n"
        "  Customize agent behavior by editing .agents/skills/shipyard-*/SKILL.md"
    )
