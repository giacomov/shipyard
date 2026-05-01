from .conftest import EVENTS_DIR, requires_act, run_act


@requires_act
def test_plan_pr_merged(substituted_template):
    workflow = substituted_template("sync-driver.yml")
    result = run_act(
        "pull_request",
        workflow,
        event_payload=EVENTS_DIR / "sync-pr-merged-plan.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
