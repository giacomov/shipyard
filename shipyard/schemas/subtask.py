import pydantic


class Subtask(pydantic.BaseModel):
    task_id: str
    title: str
    description: str
    status: str = "pending"
    blocked_by: set[str] = set()
