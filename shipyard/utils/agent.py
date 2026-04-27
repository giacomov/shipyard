"""Shared helpers for working with the claude_agent_sdk query loop."""

import json
from pathlib import Path

import click
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    Message,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from shipyard.sim import is_sim_mode


class SimSDKClient:
    """Async context manager that prints agent prompts instead of calling Claude."""

    def __init__(self, sim_plan_path: str | None = None) -> None:
        self._sim_plan_path = sim_plan_path

    async def __aenter__(self) -> "SimSDKClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def query(self, prompt: str) -> None:
        click.echo(f"[sim] Would send to agent:\n{prompt}\n")
        if self._sim_plan_path:
            Path(self._sim_plan_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self._sim_plan_path).write_text(
                "<!-- sim mode placeholder -->\n# Simulated Plan\n"
            )

    def receive_messages(self) -> "SimSDKClient":
        return self

    def __aiter__(self) -> "SimSDKClient":
        return self

    async def __anext__(self) -> Message:
        raise StopAsyncIteration


def get_sdk_client(
    options: ClaudeAgentOptions, sim_plan_path: str | None = None
) -> ClaudeSDKClient | SimSDKClient:
    """Return a real Claude SDK client, or a SimSDKClient when SHIPYARD_SIM_MODE is set."""
    if is_sim_mode():
        return SimSDKClient(sim_plan_path=sim_plan_path)
    return ClaudeSDKClient(options=options)


def _print_message(message: Message) -> None:
    """Print a message's content blocks and/or result summary."""
    match message:
        case AssistantMessage():
            for block in message.content:
                match block:
                    case TextBlock():
                        click.echo(f"[text] {block.text}")
                    case ToolUseBlock():
                        click.echo(f"[tool] {block.name} {json.dumps(block.input)[:80]}...")
                    case ThinkingBlock():
                        click.echo(f"[thinking] {block.thinking}")

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


async def receive_from_client(client: ClaudeSDKClient | SimSDKClient) -> str:
    """Drain messages from a client, printing each one. Returns collected text."""
    output_parts: list[str] = []
    async for message in client.receive_messages():
        _print_message(message)
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    output_parts.append(block.text)
        elif isinstance(message, ResultMessage):
            break
    return "\n".join(output_parts)
