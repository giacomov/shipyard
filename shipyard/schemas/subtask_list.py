import pydantic

from shipyard.schemas.subtask import Subtask


class SubtaskList(pydantic.BaseModel):
    epic_id: str = ""
    title: str
    description: str
    tasks: dict[str, Subtask] = {}
    committed: bool = False
    drafting: bool = True

    @pydantic.field_serializer("description")
    def truncate_description(self, v: str, info: pydantic.SerializationInfo) -> str:
        if info.context and info.context.get("truncate"):
            return v[:50] + "..." if len(v) > 50 else v
        return v
