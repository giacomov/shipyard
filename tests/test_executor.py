import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scripts.executor import (
    parse_implementer_status,
    parse_review_verdict,
    format_prompt,
    IssueWork,
    WorkSpec,
    ImplementerStatus,
    close_issues_body,
)


def test_parse_status_done():
    assert parse_implementer_status("some text\nStatus: DONE\nmore") == ImplementerStatus.DONE


def test_parse_status_done_with_concerns():
    assert parse_implementer_status("DONE_WITH_CONCERNS") == ImplementerStatus.DONE_WITH_CONCERNS


def test_parse_status_blocked():
    assert parse_implementer_status("BLOCKED\ncan't find module") == ImplementerStatus.BLOCKED


def test_parse_status_needs_context():
    assert parse_implementer_status("NEEDS_CONTEXT: what branch?") == ImplementerStatus.NEEDS_CONTEXT


def test_parse_status_defaults_to_blocked_on_no_match():
    assert parse_implementer_status("no status here at all") == ImplementerStatus.BLOCKED


def test_parse_review_verdict_approved():
    assert parse_review_verdict("APPROVED\nGreat work") is True


def test_parse_review_verdict_changes_requested():
    assert parse_review_verdict("CHANGES_REQUESTED\nMissing test") is False


def test_parse_review_verdict_defaults_false():
    assert parse_review_verdict("ambiguous output") is False


def test_format_prompt_substitutes_placeholders():
    template = "Task: {TASK_DESCRIPTION}\nBase: {BASE_SHA}"
    result = format_prompt(template, TASK_DESCRIPTION="Do X", BASE_SHA="abc123")
    assert result == "Task: Do X\nBase: abc123"


def test_close_issues_body():
    body = close_issues_body([5, 12, 99])
    assert "Closes #5" in body
    assert "Closes #12" in body
    assert "Closes #99" in body


@pytest.mark.asyncio
@patch("scripts.executor.run_agent", new_callable=AsyncMock)
@patch("scripts.executor.git_head_sha", return_value="abc123")
@patch("scripts.executor.git_reset_hard")
@patch("scripts.executor.post_issue_comment")
@patch("scripts.executor.create_pull_request", return_value="https://github.com/o/r/pull/9")
async def test_pipeline_happy_path(mock_pr, mock_comment, mock_reset, mock_sha, mock_agent):
    mock_agent.side_effect = [
        "Status: DONE\nFiles: foo.py",   # implementer
        "APPROVED",                        # spec reviewer
        "APPROVED",                        # code quality reviewer
    ]
    from scripts.executor import run_issue_pipeline
    issue = IssueWork(number=5, title="Do X", body="spec")
    work = WorkSpec(
        epic_number=10, epic_title="Epic", epic_body="",
        repo="owner/repo", issues=[issue]
    )
    result = await run_issue_pipeline(issue, work, base_sha="start123")
    assert result is True
    mock_reset.assert_not_called()
    mock_pr.assert_not_called()  # PR created outside pipeline


@pytest.mark.asyncio
@patch("scripts.executor.run_agent", new_callable=AsyncMock)
@patch("scripts.executor.git_head_sha", return_value="abc123")
@patch("scripts.executor.git_reset_hard")
@patch("scripts.executor.post_issue_comment")
async def test_pipeline_blocked_resets_and_comments(mock_comment, mock_reset, mock_sha, mock_agent):
    mock_agent.return_value = "BLOCKED\nCannot find module X"
    from scripts.executor import run_issue_pipeline
    issue = IssueWork(number=5, title="Do X", body="spec")
    work = WorkSpec(
        epic_number=10, epic_title="Epic", epic_body="",
        repo="owner/repo", issues=[issue]
    )
    result = await run_issue_pipeline(issue, work, base_sha="start123")
    assert result is False
    mock_reset.assert_called_once_with("start123")
    mock_comment.assert_called_once()
    comment_body = mock_comment.call_args[0][2]
    assert "BLOCKED" in comment_body


@pytest.mark.asyncio
@patch("scripts.executor.run_agent", new_callable=AsyncMock)
@patch("scripts.executor.git_head_sha", return_value="abc123")
@patch("scripts.executor.git_reset_hard")
@patch("scripts.executor.post_issue_comment")
async def test_pipeline_spec_failure_triggers_retry(mock_comment, mock_reset, mock_sha, mock_agent):
    mock_agent.side_effect = [
        "Status: DONE\nFiles: foo.py",         # implementer attempt 1
        "CHANGES_REQUESTED\nMissing test",      # spec reviewer
        "Status: DONE\nFiles: foo.py",         # implementer attempt 2
        "APPROVED",                             # spec reviewer
        "APPROVED",                             # code quality reviewer
    ]
    from scripts.executor import run_issue_pipeline
    issue = IssueWork(number=5, title="Do X", body="spec")
    work = WorkSpec(
        epic_number=10, epic_title="Epic", epic_body="",
        repo="owner/repo", issues=[issue]
    )
    result = await run_issue_pipeline(issue, work, base_sha="start123")
    assert result is True
    assert mock_agent.call_count == 5
