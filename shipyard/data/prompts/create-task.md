Use this tool to create a structured task list that divides a plan into short, manageable chunks of work with dependencies.

## Task Fields

- **task_id**: a numeric ID for this task. Use ordered, increasing integers (first task has task_id="1", second task task_id="2", and so on)
- **title**: A brief, actionable title in imperative form (e.g., "Fix authentication bug in login flow")
- **description**: What needs to be done. Provide enough details so that a different agent with no other context than this description and the code can execute the task successfully. However, do NOT do the work for the subagent. Keep the context here at a high level, do not write code line by line.

## Tips

- Create tasks with clear, specific subjects that describe the outcome
- After creating tasks, use link_tasks to set up dependencies if needed