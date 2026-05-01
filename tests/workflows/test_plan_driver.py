from .conftest import EVENTS_DIR, requires_act, run_act


@requires_act
def test_issue_labeled_plan(substituted_template):
    workflow = substituted_template("plan-driver.yml")
    result = run_act("issues", workflow, event_payload=EVENTS_DIR / "plan-issues-labeled.json")
    assert result.returncode == 0, result.stdout + result.stderr


@requires_act
def test_plan_review_changes_requested(substituted_template):
    workflow = substituted_template("plan-driver.yml")
    result = run_act(
        "pull_request_review",
        workflow,
        event_payload=EVENTS_DIR / "plan-review-changes-requested.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
