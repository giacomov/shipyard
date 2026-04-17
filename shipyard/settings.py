from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHIPYARD_")

    tasks_output_file: str = "tasks.json"
    results_file: str = "shipyard-results.json"
    plans_dir: str = "plans"
    pr_base_branch: str = "main"
    epic_status_label: str = "in-progress"
    epic_label_color: str = "0075ca"
    implementer_max_retries: int = 1

    planning_model: str = "opus-4.6"
    planning_effort: Literal["low", "medium", "high"] = "high"

    execution_model: str = "sonnet-4.6"
    execution_effort: Literal["low", "medium", "high"] = "high"


settings = Settings()
