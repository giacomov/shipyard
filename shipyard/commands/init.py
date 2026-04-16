"""shipyard init — set up the Shipyard workflow in a repository."""

import importlib.metadata
from pathlib import Path

import click


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

    if epic_dest.exists() and not force:
        raise click.ClickException(f"{epic_dest} already exists. Use --force to overwrite.")

    if not skip_plan_driver and plan_dest.exists() and not force:
        raise click.ClickException(f"{plan_dest} already exists. Use --force to overwrite.")

    if from_main:
        install_ref = "main"
    else:
        try:
            install_ref = importlib.metadata.version("shipyard")
        except importlib.metadata.PackageNotFoundError:
            install_ref = "0.1.0"

    templates_dir = Path(__file__).parent.parent / "templates"

    epic_template = templates_dir / "epic-driver.yml"
    epic_content = epic_template.read_text().replace("SHIPYARD_VERSION", install_ref)

    epic_dest.parent.mkdir(parents=True, exist_ok=True)
    epic_dest.write_text(epic_content)
    click.echo(f"Created {epic_dest}")

    if not skip_plan_driver:
        plan_template = templates_dir / "plan-driver.yml"
        plan_content = plan_template.read_text().replace("SHIPYARD_VERSION", install_ref)
        plan_dest.write_text(plan_content)
        click.echo(f"Created {plan_dest}")

    click.echo(
        "Next step: add CLAUDE_CODE_OAUTH_TOKEN as a secret in your GitHub repository settings."
    )
