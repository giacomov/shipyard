"""Tests for shipyard.commands.plan."""

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from shipyard.commands.plan import plan

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_cwd(tmp_path: Any) -> Any:
    """Change into a temporary directory for each test and restore on teardown."""
    original = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original)


def _make_agent_side_effect(plan_path: str, content: str):
    """Return an async function that writes content to plan_path, simulating the agent."""

    async def _fake_agent(*_args: Any, **_kwargs: Any) -> None:
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with open(plan_path, "w") as f:
            f.write(content)

    return _fake_agent


# ---------------------------------------------------------------------------
# 1. test_plan_requires_prompt_or_file
# ---------------------------------------------------------------------------


def test_plan_requires_prompt_or_file() -> None:
    runner = CliRunner()
    result = runner.invoke(plan, [])
    assert result.exit_code != 0
    assert "Provide" in result.output


# ---------------------------------------------------------------------------
# 2. test_plan_initial_run_creates_plan_file
# ---------------------------------------------------------------------------


def test_plan_initial_run_creates_plan_file(tmp_cwd: Any) -> None:
    runner = CliRunner()
    plan_path = str(tmp_cwd / "plans" / "i42.md")

    with patch(
        "shipyard.commands.plan.run_plan_agent",
        new=_make_agent_side_effect(plan_path, "<!-- Related to: #42 -->\n\n# Generated Plan"),
    ):
        result = runner.invoke(
            plan,
            ["--prompt", "Test issue", "--issue-number", "42"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    plan_file = tmp_cwd / "plans" / "i42.md"
    assert plan_file.exists()
    content = plan_file.read_text()
    assert content.startswith("<!-- Related to: #42 |")


# ---------------------------------------------------------------------------
# 3. test_plan_replan_updates_plan_file
# ---------------------------------------------------------------------------


def test_plan_replan_updates_plan_file(tmp_cwd: Any) -> None:
    runner = CliRunner()

    existing_plan = tmp_cwd / "existing_plan.md"
    existing_plan.write_text("# Old Plan\nOld content")

    feedback_file = tmp_cwd / "feedback.txt"
    feedback_file.write_text("Please add more detail to section 2.")

    plan_path = str(tmp_cwd / "plans" / "i42.md")

    with patch(
        "shipyard.commands.plan.run_plan_agent",
        new=_make_agent_side_effect(
            plan_path, "<!-- Related to: #42 -->\n\n# Revised Plan\nNew content"
        ),
    ):
        result = runner.invoke(
            plan,
            [
                "--pr-number",
                "99",
                "--existing-plan-path",
                str(existing_plan),
                "--review-feedback-file",
                str(feedback_file),
                "--prompt",
                "ctx",
                "--issue-number",
                "42",
            ],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    plan_file = tmp_cwd / "plans" / "i42.md"
    assert plan_file.exists()
    content = plan_file.read_text()
    assert "Revised Plan" in content


# ---------------------------------------------------------------------------
# 4. test_plan_file_has_correct_header
# ---------------------------------------------------------------------------


def test_plan_file_has_correct_header(tmp_cwd: Any) -> None:
    runner = CliRunner()
    plan_path = str(tmp_cwd / "plans" / "i42.md")

    with patch(
        "shipyard.commands.plan.run_plan_agent",
        new=_make_agent_side_effect(plan_path, "<!-- Related to: #42 -->\n\n# My Plan\nStep 1"),
    ):
        result = runner.invoke(
            plan,
            ["--prompt", "ctx", "--issue-number", "42"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    plan_file = tmp_cwd / "plans" / "i42.md"
    content = plan_file.read_text()
    assert content.startswith("<!-- Related to: #42 |")


# ---------------------------------------------------------------------------
# 5. test_plan_prepends_header_if_agent_omits_it
# ---------------------------------------------------------------------------


def test_plan_prepends_header_if_agent_omits_it(tmp_cwd: Any) -> None:
    runner = CliRunner()
    plan_path = str(tmp_cwd / "plans" / "i42.md")

    with patch(
        "shipyard.commands.plan.run_plan_agent",
        new=_make_agent_side_effect(plan_path, "# Plan Without Header\nContent here"),
    ):
        result = runner.invoke(
            plan,
            ["--prompt", "ctx", "--issue-number", "42"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    content = (tmp_cwd / "plans" / "i42.md").read_text()
    assert content.startswith("<!-- Related to: #42 |")
    assert "# Plan Without Header" in content


# ---------------------------------------------------------------------------
# 6. test_plan_raises_when_agent_does_not_write_file
# ---------------------------------------------------------------------------


def test_plan_raises_when_agent_does_not_write_file(tmp_cwd: Any) -> None:
    runner = CliRunner()

    async def _noop(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Planning agent failed to write plan file")

    with patch("shipyard.commands.plan.run_plan_agent", new=_noop):
        result = runner.invoke(
            plan,
            ["--prompt", "ctx", "--issue-number", "42"],
        )

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 7. test_run_plan_agent_retries_on_missing_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_plan_agent_retries_on_missing_file(tmp_cwd: Any) -> None:
    from shipyard.commands.plan import run_plan_agent

    plan_path = str(tmp_cwd / "plans" / "i42.md")
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)

    call_count = 0

    async def fake_receive(*_args: Any, **_kwargs: Any) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            with open(plan_path, "w") as f:
                f.write("# Plan\nContent")
        return ""

    mock_client = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("shipyard.commands.plan.get_sdk_client", return_value=mock_client),
        patch("shipyard.commands.plan.receive_from_client", side_effect=fake_receive),
    ):
        await run_plan_agent(
            prompt="test prompt",
            cwd=str(tmp_cwd),
            plan_path=plan_path,
            original_content=None,
        )

    assert call_count == 2
    assert mock_client.query.call_count == 2


# ---------------------------------------------------------------------------
# 8. test_run_plan_agent_detects_unchanged_file_on_replan
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 9. test_run_plan_agent_exhausts_retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_plan_agent_exhausts_retries(tmp_cwd: Any) -> None:
    from shipyard.commands.plan import run_plan_agent

    plan_path = str(tmp_cwd / "plans" / "i99.md")
    # Plan file is never written, so _plan_file_changed always returns False.

    mock_client = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("shipyard.commands.plan.get_sdk_client", return_value=mock_client),
        patch(
            "shipyard.commands.plan.receive_from_client", new_callable=AsyncMock, return_value=""
        ),
    ):
        with pytest.raises(RuntimeError, match="retries"):
            await run_plan_agent(
                prompt="test prompt",
                cwd=str(tmp_cwd),
                plan_path=plan_path,
                original_content=None,
            )


# ---------------------------------------------------------------------------
# 10. test_plan_cli_with_prompt_file
# ---------------------------------------------------------------------------


def test_plan_cli_with_prompt_file(tmp_cwd: Any) -> None:
    runner = CliRunner()

    prompt_file = tmp_cwd / "context.txt"
    prompt_file.write_text("this is the prompt content")

    captured: list[str] = []

    async def mock_agent(prompt: str, cwd: str, plan_path_arg: str, original_content: Any) -> None:
        captured.append(prompt)
        os.makedirs(os.path.dirname(plan_path_arg), exist_ok=True)
        with open(plan_path_arg, "w") as f:
            f.write("<!-- Related to: #5 -->\n\n# Plan")

    with patch("shipyard.commands.plan.run_plan_agent", new=mock_agent):
        result = runner.invoke(
            plan,
            ["--prompt-file", str(prompt_file), "--issue-number", "5"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    assert "this is the prompt content" in captured[0]


# ---------------------------------------------------------------------------
# 11. test_plan_cli_replan_no_existing_plan
# ---------------------------------------------------------------------------


def test_plan_cli_replan_no_existing_plan(tmp_cwd: Any) -> None:
    runner = CliRunner()

    async def mock_agent(prompt: str, cwd: str, plan_path_arg: str, original_content: Any) -> None:
        os.makedirs(os.path.dirname(plan_path_arg), exist_ok=True)
        with open(plan_path_arg, "w") as f:
            f.write("<!-- Related to: #5 -->\n\n# Plan")

    with patch("shipyard.commands.plan.run_plan_agent", new=mock_agent):
        result = runner.invoke(
            plan,
            ["--pr-number", "1", "--prompt", "ctx", "--issue-number", "5"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# 12. test_plan_cli_replan_no_feedback_file
# ---------------------------------------------------------------------------


def test_plan_cli_replan_no_feedback_file(tmp_cwd: Any) -> None:
    runner = CliRunner()

    existing_plan = tmp_cwd / "existing.md"
    existing_plan.write_text("# Old Plan\nContent")

    async def mock_agent(prompt: str, cwd: str, plan_path_arg: str, original_content: Any) -> None:
        os.makedirs(os.path.dirname(plan_path_arg), exist_ok=True)
        with open(plan_path_arg, "w") as f:
            f.write("<!-- Related to: #5 -->\n\n# Plan")

    with patch("shipyard.commands.plan.run_plan_agent", new=mock_agent):
        result = runner.invoke(
            plan,
            [
                "--pr-number",
                "1",
                "--prompt",
                "ctx",
                "--issue-number",
                "5",
                "--existing-plan-path",
                str(existing_plan),
                # No --review-feedback-file
            ],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# 13. test_run_plan_agent_detects_unchanged_file_on_replan (original #8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_plan_agent_detects_unchanged_file_on_replan(tmp_cwd: Any) -> None:
    from shipyard.commands.plan import run_plan_agent

    plan_path = str(tmp_cwd / "plans" / "i42.md")
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    original = "# Old Plan\nOld content"
    with open(plan_path, "w") as f:
        f.write(original)

    call_count = 0

    async def fake_receive(*_args: Any, **_kwargs: Any) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            with open(plan_path, "w") as f:
                f.write("# Revised Plan\nNew content")
        return ""

    mock_client = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("shipyard.commands.plan.get_sdk_client", return_value=mock_client),
        patch("shipyard.commands.plan.receive_from_client", side_effect=fake_receive),
    ):
        await run_plan_agent(
            prompt="test prompt",
            cwd=str(tmp_cwd),
            plan_path=plan_path,
            original_content=original,
        )

    assert call_count == 2
    assert mock_client.query.call_count == 2
    with open(plan_path) as f:
        assert "Revised Plan" in f.read()
