from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "generation-service"
    port: int = 8090
    database_url: str = "postgresql+psycopg2://postgres:qwer1234@localhost:5432/vibepaper_generation"
    redis_url: str = "redis://:qwer1234@localhost:6379/3"
    mq_nameserver: str = "192.168.141.128:9876"
    task_executor: str = "inline"  # inline | celery
    celery_broker_url: str = "redis://:qwer1234@localhost:6379/4"
    celery_result_backend: str = "redis://:qwer1234@localhost:6379/4"
    billing_base_url: str = "http://localhost:8084"
    identity_base_url: str = "http://localhost:8081"
    admin_base_url: str = "http://localhost:8087"
    nacos_addr: str = "192.168.141.129:8848"
    nacos_username: str = "nacos"
    nacos_password: str = "nacos"
    # 可选：强制注册 IP；留空则自动取通往 Nacos 的出站网卡 IP
    nacos_register_ip: str = ""
    storage_dir: str = r"E:\VibePaperProject\data\generation"
    freeze_ttl_minutes: int = 5
    model_timeout_seconds: int = 120
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-pro"
    # 火山方舟：优先账号有免费额度的模型
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_image_model: str = "doubao-seedream-5-0-260128"
    ark_image_size: str = "2K"
    ark_video_model: str = "doubao-seedance-1-0-pro-250528"
    ark_video_duration: int = 5
    ark_poll_interval_seconds: int = 3
    ark_poll_timeout_seconds: int = 600
    # ComfyUI（未配置则不启用）
    comfyui_base_url: str = ""
    # Mock 视频转码；留空则自动探测 PATH / WinGet / imageio-ffmpeg
    ffmpeg_path: str = ""

    class Config:
        env_prefix = "VIBEPAPER_"
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
