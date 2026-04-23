from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

type EffortLevel = Literal["low", "medium", "high"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHIPYARD_")

    tasks_output_file: str = "tasks.json"
    results_file: str = "shipyard-results.json"
    plans_dir: str = "plans"
    pr_base_branch: str = "main"
    epic_status_label: str = "in-progress"
    epic_label_color: str = "0075ca"
    implementer_max_retries: int = 1
    planner_max_retries: int = 5

    planning_model: str = "opus"
    planning_effort: EffortLevel = "high"

    execution_model: str = "sonnet"
    execution_effort: EffortLevel = "high"

    review_model: str = "sonnet"
    review_effort: EffortLevel = "high"

    revision_model: str = "sonnet"
    revision_effort: EffortLevel = "high"

    doc_model: str = "sonnet"
    doc_effort: EffortLevel = "high"
    doc_review_model: str = "sonnet"
    doc_review_effort: EffortLevel = "high"


settings = Settings()
