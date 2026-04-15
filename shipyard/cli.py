"""Shipyard CLI entry point."""

import click

from shipyard.commands.execute import execute
from shipyard.commands.find_work import find_work
from shipyard.commands.init import init
from shipyard.commands.sync import sync
from shipyard.commands.tasks import tasks


@click.group()
def main() -> None:
    """Shipyard — agentic GitHub Actions pipeline."""


main.add_command(init)
main.add_command(tasks)
main.add_command(sync)
main.add_command(find_work, name="find-work")
main.add_command(execute)
