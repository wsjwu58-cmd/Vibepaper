from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "agent-service"
    port: int = 8091
    database_url: str = "postgresql+psycopg2://postgres:qwer1234@localhost:5432/vibepaper_agent"
    redis_url: str = "redis://:qwer1234@localhost:6379/5"
    canvas_base_url: str = "http://localhost:8082"
    asset_base_url: str = "http://localhost:8083"
    billing_base_url: str = "http://localhost:8084"
    generation_base_url: str = "http://localhost:8090"
    admin_base_url: str = "http://localhost:8088"
    identity_base_url: str = "http://localhost:8081"
    nacos_addr: str = "192.168.141.129:8848"
    nacos_username: str = "nacos"
    nacos_password: str = "nacos"
    # 可选：强制注册 IP；留空则自动取通往 Nacos 的出站网卡 IP
    nacos_register_ip: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://apihub.agnes-ai.com/v1"
    llm_model: str = "agnes-2.5-flash"
    agnes_api_key: str = ""
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    max_concurrent_sessions: int = 3
    confirm_token_ttl_seconds: int = 300
    checkpoint_ttl_seconds: int = 300

    @model_validator(mode="after")
    def _fill_llm_from_agnes(self):
        if not (self.llm_api_key or "").strip() and (self.agnes_api_key or "").strip():
            self.llm_api_key = self.agnes_api_key.strip()
        return self

    def normalized_llm_base_url(self) -> str:
        """OpenAI 兼容网关：保证带 /v1。"""
        raw = (self.llm_base_url or self.agnes_base_url or "https://apihub.agnes-ai.com/v1").strip()
        base = raw.rstrip("/")
        if "agnes-ai.com" in base and not base.endswith("/v1"):
            return f"{base}/v1"
        if "deepseek.com" in base and not base.endswith("/v1"):
            return f"{base}/v1"
        return base

    def effective_llm_api_key(self) -> str:
        return (self.llm_api_key or self.agnes_api_key or "").strip()

    class Config:
        env_prefix = "VIBEPAPER_"
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
