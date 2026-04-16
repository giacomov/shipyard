"""Shared helpers for working with the claude_agent_sdk query loop."""

import click
from claude_agent_sdk import Message, ResultMessage


def report_results(message: Message) -> None:
    """Print a run summary when a ResultMessage arrives; raise on error."""
    match message:
        case ResultMessage():
            usage = message.usage or {}
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            lines: list[str] = [f"tokens: {input_tokens} in / {output_tokens} out"]

            server_tools = usage.get("server_tool_use", {})
            active = {k: v for k, v in server_tools.items() if v}
            if active:
                lines.append("tools: " + ", ".join(f"{k}={v}" for k, v in active.items()))

            if message.permission_denials:
                lines.append(
                    "permission denials: " + ", ".join(str(d) for d in message.permission_denials)
                )

            if message.errors:
                lines.append("errors: " + ", ".join(message.errors))

            click.echo("[agent] " + " | ".join(lines), err=True)

            if message.is_error:
                raise RuntimeError(message.result or "Agent returned an error")
