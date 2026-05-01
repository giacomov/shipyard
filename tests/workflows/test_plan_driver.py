from .conftest import EVENTS_DIR, requires_act, run_act


@requires_act
def test_issue_comment_ship_plan(substituted_template):
    workflow = substituted_template("plan-driver.yml")
    result = run_act(
        "issue_comment",
        workflow,
        event_payload=EVENTS_DIR / "plan-issue-comment-ship-plan.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr


@requires_act
def test_issue_comment_ship_replan(substituted_template):
    workflow = substituted_template("plan-driver.yml")
    result = run_act(
        "issue_comment",
        workflow,
        event_payload=EVENTS_DIR / "plan-issue-comment-ship-replan.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
