from functools import lru_cache

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
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-pro"

    def normalized_llm_base_url(self) -> str:
        """DeepSeek 兼容 OpenAI：保证带 /v1，避免 /chat/completions 404。"""
        base = (self.llm_base_url or "https://api.deepseek.com/v1").rstrip("/")
        if "deepseek.com" in base and not base.endswith("/v1"):
            return f"{base}/v1"
        return base
    max_concurrent_sessions: int = 3
    confirm_token_ttl_seconds: int = 300
    checkpoint_ttl_seconds: int = 300

    class Config:
        env_prefix = "VIBEPAPER_"
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
