"""Shared helpers for working with the claude_agent_sdk query loop."""

from claude_agent_sdk import AssistantMessage


def report_error(response: AssistantMessage) -> None:
    """Raise RuntimeError if the assistant message carries an error."""
    if response.error is not None:
        raise RuntimeError(f"Agent error: {response.error}")
