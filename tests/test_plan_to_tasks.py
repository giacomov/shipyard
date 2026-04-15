import json
from pathlib import Path

import pytest

from shipyard.commands.tasks import parse_plan, plan_to_tasks_dict, validate_plan

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_title_from_h1():
    plan = parse_plan(
        "# My Feature Plan\n\n**Goal:** Do X.\n\n### Task 1: Setup\n\n**Depends on:** (none)\n\nDesc.\n"
    )
    assert plan.title == "My Feature Plan"


def test_parses_goal_as_body():
    plan = parse_plan(
        "# Title\n\n**Goal:** Build Y.\n\n### Task 1: A\n\n**Depends on:** (none)\n\nDesc.\n"
    )
    assert plan.body == "Build Y."


def test_parses_tasks_by_header():
    plan = parse_plan(
        "# T\n\n**Goal:** X.\n\n### Task 1: Alpha\n\n**Depends on:** (none)\n\nAlpha desc.\n\n### Task 2: Beta\n\n**Depends on:** Task 1\n\nBeta desc.\n"
    )
    assert len(plan.tasks) == 2
    assert plan.tasks[0].id == "1"
    assert plan.tasks[0].subject == "Alpha"
    assert plan.tasks[1].id == "2"
    assert plan.tasks[1].subject == "Beta"


def test_depends_on_none_gives_empty_list():
    plan = parse_plan("# T\n\n**Goal:** X.\n\n### Task 1: A\n\n**Depends on:** (none)\n\nDesc.\n")
    assert plan.tasks[0].dependencies == []


def test_depends_on_task_1_and_3():
    text = (
        "# T\n\n**Goal:** X.\n\n"
        "### Task 1: A\n\n**Depends on:** (none)\n\nDesc.\n\n"
        "### Task 2: B\n\n**Depends on:** (none)\n\nDesc.\n\n"
        "### Task 3: C\n\n**Depends on:** Task 1, Task 2\n\nDesc.\n"
    )
    plan = parse_plan(text)
    assert plan.tasks[2].dependencies == ["1", "2"]


def test_validates_unknown_dependency_raises():
    plan = parse_plan("# T\n\n**Goal:** X.\n\n### Task 1: A\n\n**Depends on:** Task 99\n\nDesc.\n")
    with pytest.raises(ValueError, match="unknown dependency"):
        validate_plan(plan)


def test_description_excludes_header_and_depends_on_lines():
    plan = parse_plan(
        "# T\n\n**Goal:** X.\n\n### Task 1: Setup\n\n**Depends on:** (none)\n\nActual description here.\n"
    )
    assert "### Task 1" not in plan.tasks[0].description
    assert "**Depends on:**" not in plan.tasks[0].description
    assert "Actual description here." in plan.tasks[0].description


def test_full_round_trip():
    plan_text = (FIXTURES / "sample_plan.md").read_text()
    expected = json.loads((FIXTURES / "sample_tasks.json").read_text())
    plan = parse_plan(plan_text)
    validate_plan(plan)
    result = plan_to_tasks_dict(plan)
    assert result == expected
