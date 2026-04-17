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

    planning_model = "opus-4.6"
    planning_effort = "high"

    execution_model = "sonnet-4.6"
    execution_effort = "high"


settings = Settings()
