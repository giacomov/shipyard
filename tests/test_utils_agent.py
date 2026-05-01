"""Tests for shipyard.utils.agent."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from shipyard.utils.agent import (
    SimSDKClient,
    _print_message,
    get_sdk_client,
    receive_from_client,
)

# ---------------------------------------------------------------------------
# SimSDKClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sim_client_context_manager() -> None:
    async with SimSDKClient() as client:
        assert client is not None


@pytest.mark.asyncio
async def test_sim_client_query_prints(capsys) -> None:
    client = SimSDKClient()
    await client.query("Hello, agent!")
    assert "Hello, agent!" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_sim_client_query_writes_plan_file(tmp_path: Path) -> None:
    plan_path = str(tmp_path / "plans" / "i1.md")
    client = SimSDKClient(sim_plan_path=plan_path)
    await client.query("Write a plan")
    assert Path(plan_path).exists()
    assert "sim mode" in Path(plan_path).read_text()


@pytest.mark.asyncio
async def test_sim_client_receive_messages_empty() -> None:
    client = SimSDKClient()
    messages = [msg async for msg in client.receive_messages()]
    assert messages == []


# ---------------------------------------------------------------------------
# get_sdk_client
# ---------------------------------------------------------------------------


def test_get_sdk_client_returns_sim_client_in_sim_mode() -> None:
    with patch.dict(os.environ, {"SHIPYARD_SIM_MODE": "1"}):
        client = get_sdk_client(ClaudeAgentOptions())
    assert isinstance(client, SimSDKClient)


def test_get_sdk_client_returns_sim_client_with_plan_path(tmp_path: Path) -> None:
    plan_path = str(tmp_path / "plan.md")
    with patch.dict(os.environ, {"SHIPYARD_SIM_MODE": "1"}):
        client = get_sdk_client(ClaudeAgentOptions(), sim_plan_path=plan_path)
    assert isinstance(client, SimSDKClient)


# ---------------------------------------------------------------------------
# receive_from_client
# ---------------------------------------------------------------------------


class _MessageClient:
    """Minimal async iterator that yields a fixed sequence of SDK messages."""

    def __init__(self, messages: list) -> None:
        self._iter = iter(messages)

    def receive_messages(self) -> "_MessageClient":
        return self

    def __aiter__(self) -> "_MessageClient":
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_receive_from_client_sim_returns_empty_string() -> None:
    client = SimSDKClient()
    result = await receive_from_client(client)
    assert result == ""


@pytest.mark.asyncio
async def test_receive_from_client_collects_text_blocks() -> None:
    assistant_msg = AssistantMessage(
        content=[TextBlock("hello"), TextBlock("world")], model="claude"
    )
    result_msg = ResultMessage(
        subtype="result",
        duration_ms=10,
        duration_api_ms=10,
        is_error=False,
        num_turns=1,
        session_id="s1",
        usage={"input_tokens": 1, "output_tokens": 2},
    )
    client = _MessageClient([assistant_msg, result_msg])
    text = await receive_from_client(client)
    assert text == "hello\nworld"


@pytest.mark.asyncio
async def test_receive_from_client_skips_non_text_blocks() -> None:
    assistant_msg = AssistantMessage(
        content=[ToolUseBlock("id1", "bash", {"command": "ls"}), TextBlock("done")],
        model="claude",
    )
    result_msg = ResultMessage(
        subtype="result",
        duration_ms=10,
        duration_api_ms=10,
        is_error=False,
        num_turns=1,
        session_id="s1",
    )
    client = _MessageClient([assistant_msg, result_msg])
    text = await receive_from_client(client)
    assert text == "done"


# ---------------------------------------------------------------------------
# _print_message
# ---------------------------------------------------------------------------


def test_print_message_text_block(capsys) -> None:
    msg = AssistantMessage(content=[TextBlock("hello world")], model="claude")
    _print_message(msg)
    assert "[text] hello world" in capsys.readouterr().out


def test_print_message_tool_use_block(capsys) -> None:
    msg = AssistantMessage(content=[ToolUseBlock("id1", "bash", {"command": "ls"})], model="claude")
    _print_message(msg)
    assert "[tool] bash" in capsys.readouterr().out


def test_print_message_thinking_block(capsys) -> None:
    msg = AssistantMessage(content=[ThinkingBlock("I think therefore I am", "sig")], model="claude")
    _print_message(msg)
    assert "[thinking]" in capsys.readouterr().out


def test_print_message_result_prints_tokens(capsys) -> None:
    msg = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=100,
        is_error=False,
        num_turns=1,
        session_id="s1",
        usage={"input_tokens": 42, "output_tokens": 7},
    )
    _print_message(msg)
    captured = capsys.readouterr()
    assert "42 in" in captured.err
    assert "7 out" in captured.err


def test_print_message_result_active_tools(capsys) -> None:
    msg = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=100,
        is_error=False,
        num_turns=1,
        session_id="s1",
        usage={"input_tokens": 1, "output_tokens": 1, "server_tool_use": {"web_search": 3}},
    )
    _print_message(msg)
    assert "web_search=3" in capsys.readouterr().err


def test_print_message_result_errors_listed(capsys) -> None:
    msg = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=100,
        is_error=False,
        num_turns=1,
        session_id="s1",
        errors=["something failed"],
    )
    _print_message(msg)
    assert "something failed" in capsys.readouterr().err


def test_print_message_result_permission_denials(capsys) -> None:
    msg = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=100,
        is_error=False,
        num_turns=1,
        session_id="s1",
        permission_denials=["tool:bash"],
    )
    _print_message(msg)
    assert "permission denials" in capsys.readouterr().err


def test_print_message_result_error_raises() -> None:
    msg = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=100,
        is_error=True,
        num_turns=1,
        session_id="s1",
        result="Agent exploded",
    )
    with pytest.raises(RuntimeError, match="Agent exploded"):
        _print_message(msg)
