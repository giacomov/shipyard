from .conftest import EVENTS_DIR, requires_act, run_act


@requires_act
def test_issue_comment_ship_run(substituted_template):
    workflow = substituted_template("epic-driver.yml")
    result = run_act(
        "issue_comment",
        workflow,
        event_payload=EVENTS_DIR / "epic-issue-comment-ship-run.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr


@requires_act
def test_pr_merged_to_epic_branch(substituted_template):
    workflow = substituted_template("epic-driver.yml")
    result = run_act("pull_request", workflow, event_payload=EVENTS_DIR / "epic-pr-merged.json")
    assert result.returncode == 0, result.stdout + result.stderr
