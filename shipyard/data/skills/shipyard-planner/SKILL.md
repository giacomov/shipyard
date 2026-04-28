---
name: shipyard-planner
description: Generates an implementation plan for a GitHub issue. Use when shipyard asks to write a plan for an issue.
user-invocable: false
---

Read the issue context and the codebase, then write an implementation plan in Markdown.

Each task in the plan will become its own PR, so group work to keep the number of tasks
small without sacrificing the focus and cohesiveness of each PR.
