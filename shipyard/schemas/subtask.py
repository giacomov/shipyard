import pydantic


class Subtask(pydantic.BaseModel):
    task_id: str
    title: str
    description: str
    blocked_by: set[str] = set()
