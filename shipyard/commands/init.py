"""shipyard init — set up the Shipyard workflow in a repository."""

import importlib.metadata
from pathlib import Path

import click


@click.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing workflow file")
def init(path: str, force: bool) -> None:
    """Set up the Shipyard epic-driver workflow in a repository.

    PATH defaults to the current directory.
    """
    dest = Path(path) / ".github" / "workflows" / "epic-driver.yml"

    if dest.exists() and not force:
        raise click.ClickException(f"{dest} already exists. Use --force to overwrite.")

    try:
        version = importlib.metadata.version("shipyard")
    except importlib.metadata.PackageNotFoundError:
        version = "0.1.0"

    template_path = Path(__file__).parent.parent / "templates" / "epic-driver.yml"
    content = template_path.read_text().replace("SHIPYARD_VERSION", version)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)

    click.echo(f"Created {dest}")
    click.echo(
        "Next step: add CLAUDE_CODE_OAUTH_TOKEN as a secret in your GitHub repository settings."
    )
