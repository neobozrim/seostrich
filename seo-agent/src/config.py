from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


# OpenAI-compatible endpoints per provider. token-plan queues burst traffic
# (4+ rapid calls get held open for minutes), which is what stalled the large
# clustering call; the cloud API does not queue.
PROVIDER_BASE_URLS = {
    "cloud": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "token_plan": "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
}


class Settings(BaseSettings):
    # "cloud" (default) or "token_plan". Selects which key and base URL to use.
    llm_provider: str = Field(default="cloud", alias="LLM_PROVIDER")

    qwen_cloud_api_key: str = Field(default="", alias="QWEN_CLOUD_API_KEY")
    qwen_token_plan_api_key: str = Field(default="", alias="QWEN_TOKEN_PLAN_API_KEY")

    # Explicit override; when unset the provider's default URL is used.
    qwen_base_url_override: str = Field(default="", alias="QWEN_BASE_URL")
    qwen_model: str = Field(default="qwen3.6-plus", alias="QWEN_MODEL")
    # Mechanical nodes (grouping, extraction) gain nothing from a reasoning
    # model and pay for it in latency: clustering took 254s on qwen3.8-max
    # (9,464 reasoning tokens) vs 44s on flash for the same ten clusters.
    qwen_model_fast: str = Field(default="qwen3.8-flash", alias="QWEN_MODEL_FAST")

    @property
    def provider(self) -> str:
        p = (self.llm_provider or "cloud").strip().lower().replace("-", "_")
        return p if p in PROVIDER_BASE_URLS else "cloud"

    @property
    def qwen_api_key(self) -> str:
        """Key for the selected provider, falling back to whichever is set."""
        if self.provider == "token_plan":
            return self.qwen_token_plan_api_key or self.qwen_cloud_api_key
        return self.qwen_cloud_api_key or self.qwen_token_plan_api_key

    @property
    def qwen_base_url(self) -> str:
        return self.qwen_base_url_override or PROVIDER_BASE_URLS[self.provider]

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

    # Hard cap on DataForSEO API calls per pipeline run (chat session reuses
    # its run id, so the cap spans follow-up messages in the same session).
    dfs_max_calls_per_run: int = Field(default=25, alias="DFS_MAX_CALLS_PER_RUN")

    # Post-run reflection tail (outcome summary + memory synthesis + Braintrust
    # + self-learning). ~10 extra LLM calls per run, each carrying the full
    # session JSON. Off by default: it costs more than the whole pipeline and
    # produces nothing the user sees. Set AGENT_REFLECTION=on to re-enable.
    agent_reflection: str = Field(default="off", alias="AGENT_REFLECTION")

    mock_llm: bool = Field(default=False, alias="MOCK_LLM")
    mock_dfs: bool = Field(default=False, alias="MOCK_DFS")

    # Local-only pacing: token-plan queues burst traffic (4+ rapid calls),
    # so space LLM calls when set. Production leaves it unset (0).
    llm_min_interval: float = Field(default=0.0, alias="LLM_MIN_INTERVAL_SECONDS")

    class Config:
        env_file = str(ENV_FILE) if ENV_FILE.exists() else None
        extra = "ignore"


settings = Settings()


def reflection_enabled() -> bool:
    """True when the post-run reflection tail should run (default: off)."""
    return settings.agent_reflection.strip().lower() in ("1", "on", "true", "yes")
