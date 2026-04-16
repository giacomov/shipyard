"""Shipyard CLI entry point."""

import click

from shipyard.commands.execute import execute
from shipyard.commands.find_work import find_work
from shipyard.commands.init import init
from shipyard.commands.plan import plan
from shipyard.commands.publish import publish_execution
from shipyard.commands.sync import sync
from shipyard.commands.tasks import tasks
from shipyard.utils.github_event import extract_github_event


@click.group()
def main() -> None:
    """Shipyard — agentic GitHub Actions pipeline."""


main.add_command(init)
main.add_command(tasks)
main.add_command(sync)
main.add_command(find_work, name="find-work")
main.add_command(execute)
main.add_command(plan)
main.add_command(publish_execution, name="publish-execution")
main.add_command(extract_github_event, name="extract-github-event")
