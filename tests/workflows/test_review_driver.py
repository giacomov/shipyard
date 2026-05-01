from .conftest import EVENTS_DIR, requires_act, run_act


@requires_act
def test_changes_requested_on_shipyard_branch(substituted_template):
    workflow = substituted_template("review-driver.yml")
    result = run_act(
        "pull_request_review",
        workflow,
        event_payload=EVENTS_DIR / "review-driver-changes-requested.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr
