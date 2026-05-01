from .conftest import EVENTS_DIR, requires_act, run_act


@requires_act
def test_issue_labeled_in_progress(substituted_template):
    workflow = substituted_template("epic-driver.yml")
    result = run_act("issues", workflow, event_payload=EVENTS_DIR / "epic-issues-labeled.json")
    assert result.returncode == 0, result.stdout + result.stderr


@requires_act
def test_pr_merged_to_epic_branch(substituted_template):
    workflow = substituted_template("epic-driver.yml")
    result = run_act("pull_request", workflow, event_payload=EVENTS_DIR / "epic-pr-merged.json")
    assert result.returncode == 0, result.stdout + result.stderr


@requires_act
def test_workflow_dispatch(substituted_template):
    workflow = substituted_template("epic-driver.yml")
    result = run_act("workflow_dispatch", workflow, inputs={"issue_number": "42"})
    assert result.returncode == 0, result.stdout + result.stderr
