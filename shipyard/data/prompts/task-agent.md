## Your task

Read the implementation plan at {plan_path}, explore the repo if needed, and create tasks with dependencies for it
using the create_task tool.

## Requirements

- Each task will be implemented and merged as a separate Pull Request (PR). Group work so each PR is focused and cohesive, and keep the total number of tasks small.
- Each task should be self-contained: provide enough details so that a sub-agent will be able to execute it according to the plan. However, do NOT do all the work for the subagent. Keep the context at a high level, aim for context and not implementation.

## How to accomplish your task

- Read the plan, then explore the code if needed to gather enough context.
- Subdivide the plan into a small number of focused, cohesive tasks
- For each task call create_task with:
    - subject: short task title
    - description: what must be implemented (be specific). This description must contain all the details that an implementation agent will need to implement this task. However, keep the context at a high level, aim for context and not implementation.
- Then call link_tasks to establish dependencies between the tasks

After you are done, you will receive back a JSON blob describing the structure you created. If you need to make corrections, use the delete_task and the unlink_tasks tools as needed.

## Tips

* First use create_task to create each task one by one
* Then use link_tasks to established the dependencies