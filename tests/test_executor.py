from unittest.mock import AsyncMock, patch

import pytest

from shipyard.commands.execute import (
    ImplementerStatus,
    IssueWork,
    WorkSpec,
    close_issues_body,
    format_prompt,
    parse_implementer_status,
    parse_review_verdict,
)


def _work(**kwargs) -> WorkSpec:
    defaults = dict(epic_number=10, epic_title="Epic", epic_body="", repo="owner/repo", issues=[])
    return WorkSpec(**{**defaults, **kwargs})


def _issue(**kwargs) -> IssueWork:
    defaults = dict(number=5, title="Do X", body="spec")
    return IssueWork(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# parse_implementer_status
# ---------------------------------------------------------------------------


def test_parse_status_done():
    assert parse_implementer_status("some text\nStatus: DONE\nmore") == ImplementerStatus.DONE


def test_parse_status_done_with_concerns():
    assert parse_implementer_status("DONE_WITH_CONCERNS") == ImplementerStatus.DONE_WITH_CONCERNS


def test_parse_status_done_with_concerns_takes_priority_over_done():
    # DONE is a substring of DONE_WITH_CONCERNS; longer match must win
    assert (
        parse_implementer_status("DONE_WITH_CONCERNS: minor issues")
        == ImplementerStatus.DONE_WITH_CONCERNS
    )


def test_parse_status_blocked():
    assert parse_implementer_status("BLOCKED\ncan't find module") == ImplementerStatus.BLOCKED


def test_parse_status_needs_context():
    assert (
        parse_implementer_status("NEEDS_CONTEXT: what branch?") == ImplementerStatus.NEEDS_CONTEXT
    )


def test_parse_status_defaults_to_blocked_on_no_match():
    assert parse_implementer_status("no status here at all") == ImplementerStatus.BLOCKED


def test_parse_status_uses_last_matching_line():
    # If DONE appears early and BLOCKED late, BLOCKED wins (scans in reverse)
    assert parse_implementer_status("DONE\nsome work\nBLOCKED") == ImplementerStatus.BLOCKED


def test_parse_status_case_insensitive():
    assert parse_implementer_status("done") == ImplementerStatus.DONE


# ---------------------------------------------------------------------------
# parse_review_verdict
# ---------------------------------------------------------------------------


def test_parse_review_verdict_approved():
    assert parse_review_verdict("APPROVED\nGreat work") is True


def test_parse_review_verdict_changes_requested():
    assert parse_review_verdict("CHANGES_REQUESTED\nMissing test") is False


def test_parse_review_verdict_defaults_false():
    assert parse_review_verdict("ambiguous output") is False


def test_parse_review_verdict_not_approved_is_false():
    assert parse_review_verdict("NOT APPROVED — needs work") is False


def test_parse_review_verdict_changes_requested_overrides_approved():
    # Both tokens present — CHANGES_REQUESTED must win
    assert parse_review_verdict("APPROVED but also CHANGES_REQUESTED") is False


# ---------------------------------------------------------------------------
# format_prompt / close_issues_body
# ---------------------------------------------------------------------------


def test_format_prompt_substitutes_placeholders():
    template = "Task: {TASK_DESCRIPTION}\nBase: {BASE_SHA}"
    result = format_prompt(template, TASK_DESCRIPTION="Do X", BASE_SHA="abc123")
    assert result == "Task: Do X\nBase: abc123"


def test_format_prompt_leaves_unknown_placeholders_intact():
    assert format_prompt("{FOO} {BAR}", FOO="x") == "x {BAR}"


def test_close_issues_body():
    body = close_issues_body([5, 12, 99])
    assert "Closes #5" in body
    assert "Closes #12" in body
    assert "Closes #99" in body


def test_close_issues_body_single():
    body = close_issues_body([1])
    assert "Closes #1" in body


# ---------------------------------------------------------------------------
# run_issue_pipeline — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_happy_path(mock_comment, mock_reset, mock_agent):
    mock_agent.side_effect = [
        "Status: DONE\nFiles: foo.py",
        "APPROVED",
        "APPROVED",
    ]
    from shipyard.commands.execute import run_issue_pipeline

    issue = _issue()
    result = await run_issue_pipeline(issue, _work(), base_sha="start123")
    assert result is True
    mock_reset.assert_not_called()
    mock_comment.assert_not_called()


# ---------------------------------------------------------------------------
# run_issue_pipeline — implementer failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_blocked_resets_and_comments(mock_comment, mock_reset, mock_agent):
    mock_agent.return_value = "BLOCKED\nCannot find module X"
    from shipyard.commands.execute import run_issue_pipeline

    result = await run_issue_pipeline(_issue(), _work(), base_sha="start123")
    assert result is False
    mock_reset.assert_called_once_with("start123")
    comment_body = mock_comment.call_args[0][2]
    assert "BLOCKED" in comment_body


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_needs_context_resets_and_comments(mock_comment, mock_reset, mock_agent):
    mock_agent.return_value = "NEEDS_CONTEXT: missing branch info"
    from shipyard.commands.execute import run_issue_pipeline

    result = await run_issue_pipeline(_issue(), _work(), base_sha="sha0")
    assert result is False
    mock_reset.assert_called_once_with("sha0")
    comment_body = mock_comment.call_args[0][2]
    assert "NEEDS_CONTEXT" in comment_body


# ---------------------------------------------------------------------------
# run_issue_pipeline — spec review retry / terminal failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_spec_failure_triggers_retry(mock_comment, mock_reset, mock_agent):
    mock_agent.side_effect = [
        "Status: DONE\nFiles: foo.py",  # implementer attempt 1
        "CHANGES_REQUESTED\nMissing test",  # spec reviewer attempt 1
        "Status: DONE\nFiles: foo.py",  # implementer attempt 2
        "APPROVED",  # spec reviewer attempt 2
        "APPROVED",  # quality reviewer attempt 2
    ]
    from shipyard.commands.execute import run_issue_pipeline

    result = await run_issue_pipeline(_issue(), _work(), base_sha="start123")
    assert result is True
    assert mock_agent.call_count == 5
    # Reset once between attempts
    mock_reset.assert_called_once_with("start123")
    mock_comment.assert_not_called()


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_spec_terminal_failure_comments(mock_comment, mock_reset, mock_agent):
    # Both attempts fail spec review — max_retries=1 means 2 total attempts
    mock_agent.side_effect = [
        "DONE",
        "CHANGES_REQUESTED",  # attempt 1 spec fail
        "DONE",
        "CHANGES_REQUESTED",  # attempt 2 spec fail → terminal
    ]
    from shipyard.commands.execute import run_issue_pipeline

    result = await run_issue_pipeline(_issue(), _work(), base_sha="sha0", max_retries=1)
    assert result is False
    mock_comment.assert_called_once()
    comment_body = mock_comment.call_args[0][2]
    assert "SPEC_FAILED" in comment_body


# ---------------------------------------------------------------------------
# run_issue_pipeline — quality review retry / terminal failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_quality_failure_triggers_retry(mock_comment, mock_reset, mock_agent):
    mock_agent.side_effect = [
        "DONE",  # implementer 1
        "APPROVED",  # spec 1
        "CHANGES_REQUESTED",  # quality 1 → retry
        "DONE",  # implementer 2
        "APPROVED",  # spec 2
        "APPROVED",  # quality 2
    ]
    from shipyard.commands.execute import run_issue_pipeline

    result = await run_issue_pipeline(_issue(), _work(), base_sha="sha0", max_retries=1)
    assert result is True
    assert mock_agent.call_count == 6
    mock_comment.assert_not_called()


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_agent", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_reset_hard")
@patch("shipyard.commands.execute.post_issue_comment")
async def test_pipeline_quality_terminal_failure_comments(mock_comment, mock_reset, mock_agent):
    mock_agent.side_effect = [
        "DONE",
        "APPROVED",
        "CHANGES_REQUESTED",  # attempt 1 quality fail
        "DONE",
        "APPROVED",
        "CHANGES_REQUESTED",  # attempt 2 quality fail → terminal
    ]
    from shipyard.commands.execute import run_issue_pipeline

    result = await run_issue_pipeline(_issue(), _work(), base_sha="sha0", max_retries=1)
    assert result is False
    mock_comment.assert_called_once()
    comment_body = mock_comment.call_args[0][2]
    assert "QUALITY_FAILED" in comment_body


# ---------------------------------------------------------------------------
# run_all_issues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_issue_pipeline", new_callable=AsyncMock)
@patch("shipyard.commands.execute.git_head_sha", return_value="abc")
async def test_run_all_issues_returns_results_dict(mock_sha, mock_pipeline):
    mock_pipeline.side_effect = [True, False]
    from shipyard.commands.execute import run_all_issues

    issues = [_issue(number=1, title="A"), _issue(number=2, title="B")]
    work = _work(issues=issues)
    results = await run_all_issues(work)
    assert results == {1: True, 2: False}


@pytest.mark.asyncio
@patch("shipyard.commands.execute.run_issue_pipeline", new_callable=AsyncMock, return_value=True)
@patch("shipyard.commands.execute.git_head_sha", return_value="abc")
async def test_run_all_issues_all_success(mock_sha, mock_pipeline):
    from shipyard.commands.execute import run_all_issues

    issues = [_issue(number=i, title=f"T{i}") for i in range(3)]
    work = _work(issues=issues)
    results = await run_all_issues(work)
    assert all(results.values())
    assert len(results) == 3


# ---------------------------------------------------------------------------
# execute command — env var guards
# ---------------------------------------------------------------------------


def test_execute_command_missing_work_json(monkeypatch):
    from click.testing import CliRunner

    from shipyard.commands.execute import execute

    monkeypatch.delenv("WORK_JSON", raising=False)
    runner = CliRunner()
    result = runner.invoke(execute)
    assert result.exit_code != 0
    assert "WORK_JSON" in result.output
