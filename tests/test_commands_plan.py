"""Tests for shipyard.commands.plan."""

import os
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from shipyard.commands.plan import _strip_outer_fence, plan

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

    with patch("shipyard.commands.plan.asyncio.run", return_value="# Generated Plan\nDetails here"):
        result = runner.invoke(
            plan,
            ["--prompt", "Test issue", "--issue-number", "42"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    plan_file = tmp_cwd / "plans" / "i42.md"
    assert plan_file.exists()
    content = plan_file.read_text()
    assert content.startswith("<!-- Related to: #42 -->")


# ---------------------------------------------------------------------------
# 3. test_plan_replan_updates_plan_file
# ---------------------------------------------------------------------------


def test_plan_replan_updates_plan_file(tmp_cwd: Any) -> None:
    runner = CliRunner()

    existing_plan = tmp_cwd / "existing_plan.md"
    existing_plan.write_text("# Old Plan\nOld content")

    feedback_file = tmp_cwd / "feedback.txt"
    feedback_file.write_text("Please add more detail to section 2.")

    with patch("shipyard.commands.plan.asyncio.run", return_value="# Revised Plan\nNew content"):
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

    with patch("shipyard.commands.plan.asyncio.run", return_value="# My Plan\nStep 1\nStep 2"):
        result = runner.invoke(
            plan,
            ["--prompt", "ctx", "--issue-number", "42"],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    plan_file = tmp_cwd / "plans" / "i42.md"
    content = plan_file.read_text()
    assert content.startswith("<!-- Related to: #42 -->")


# ---------------------------------------------------------------------------
# 5. test_strip_outer_fence
# ---------------------------------------------------------------------------


def test_strip_outer_fence_removes_markdown_fence() -> None:
    text = "```markdown\n# My Plan\n\nStep 1\n```"
    assert _strip_outer_fence(text) == "# My Plan\n\nStep 1"


def test_strip_outer_fence_removes_plain_fence() -> None:
    text = "```\n# My Plan\n\nStep 1\n```"
    assert _strip_outer_fence(text) == "# My Plan\n\nStep 1"


def test_strip_outer_fence_leaves_unfenced_text_unchanged() -> None:
    text = "# My Plan\n\nStep 1"
    assert _strip_outer_fence(text) == "# My Plan\n\nStep 1"


def test_strip_outer_fence_strips_surrounding_whitespace() -> None:
    text = "  \n# My Plan\n\nStep 1\n  "
    assert _strip_outer_fence(text) == "# My Plan\n\nStep 1"


def test_strip_outer_fence_partial_fence_not_removed() -> None:
    text = "```markdown\n# My Plan\n\nStep 1"
    assert _strip_outer_fence(text) == "```markdown\n# My Plan\n\nStep 1"
