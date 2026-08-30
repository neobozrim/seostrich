from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    qwen_api_key: str = Field(default="", alias="QWEN_TOKEN_PLAN_API_KEY")
    qwen_base_url: str = Field(
        default="https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        alias="QWEN_BASE_URL",
    )
    qwen_model: str = Field(default="qwen3.6-plus", alias="QWEN_MODEL")

    dataforseo_login: str = Field(default="", alias="DATAFORSEO_LOGIN")
    dataforseo_password: str = Field(default="", alias="DATAFORSEO_PASSWORD")
    dataforseo_base_url: str = Field(
        default="https://api.dataforseo.com", alias="DATAFORSEO_BASE_URL"
    )

    bing_wmt_api_key: str = Field(default="", alias="BING_WEBMASTER_TOOLS_API_KEY")

    pagespeed_api_key: str = Field(default="", alias="PAGESPEED_API_KEY")

    gsc_credentials_path: str = Field(
        default="gsc-console-creds.json", alias="GSC_CREDENTIALS_PATH"
    )

    braintrust_api_key: str = Field(default="", alias="BRAINTRUST_API_KEY")
    braintrust_project_id: str = Field(default="", alias="BRAINTRUST_PROJECT_ID")

    fal_key: str = Field(default="", alias="FAL_KEY")

    budget_per_job_dfs: float = 1.0
    budget_per_job_llm: float = 5.0

    mock_llm: bool = Field(default=False, alias="MOCK_LLM")
    mock_dfs: bool = Field(default=False, alias="MOCK_DFS")

    class Config:
        env_file = str(ENV_FILE) if ENV_FILE.exists() else None
        extra = "ignore"


settings = Settings()
