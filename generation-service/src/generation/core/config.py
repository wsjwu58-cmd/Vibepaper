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
    canvas_base_url: str = "http://localhost:8082"
    agent_base_url: str = "http://localhost:8091"
    internal_service_token: str = ""
    nacos_addr: str = "192.168.141.129:8848"
    nacos_username: str = "nacos"
    nacos_password: str = "nacos"
    # 可选：强制注册 IP；留空则自动取通往 Nacos 的出站网卡 IP
    nacos_register_ip: str = ""
    storage_dir: str = r"E:\VibePaperProject\data\generation"
    freeze_ttl_minutes: int = 5
    model_timeout_seconds: int = 120
    llm_api_key: str = ""
    llm_base_url: str = "https://apihub.agnes-ai.com/v1"
    llm_model: str = "agnes-2.5-flash"
    # Agnes AI：图像 / 视频生成（https://apihub.agnes-ai.com/v1）
    agnes_api_key: str = ""
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_image_model: str = "agnes-image-2.1-flash"
    agnes_image_size: str = "2K"
    agnes_video_model: str = "agnes-video-v2.0"
    agnes_video_duration: int = 5
    # Agnes 状态查询有频率限制；过短会触发 HTTP 429
    agnes_poll_interval_seconds: int = 10
    agnes_poll_timeout_seconds: int = 600
    # 火山方舟：旧图/视频保留配置；当前默认走 Agnes
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_image_model: str = "doubao-seedream-5-0-260128"
    ark_image_size: str = "2K"
    ark_video_model: str = "doubao-seedance-1-5-pro-251215"
    ark_video_duration: int = 5
    ark_poll_interval_seconds: int = 3
    ark_poll_timeout_seconds: int = 600
    # ComfyUI（未配置则不启用）
    comfyui_base_url: str = ""
    # Mock 视频转码；留空则自动探测 PATH / WinGet / imageio-ffmpeg
    ffmpeg_path: str = ""
    # 火山语音（豆包 TTS，与方舟 ARK Key 分开）
    speech_app_id: str = ""
    speech_token: str = ""
    speech_cluster: str = "volcano_tts"

    def effective_llm_api_key(self) -> str:
        return (self.llm_api_key or self.agnes_api_key or "").strip()

    def normalized_llm_base_url(self) -> str:
        raw = (self.llm_base_url or self.agnes_base_url or "https://apihub.agnes-ai.com/v1").strip()
        base = raw.rstrip("/")
        if ("agnes-ai.com" in base or "deepseek.com" in base) and not base.endswith("/v1"):
            return f"{base}/v1"
        return base

    class Config:
        env_prefix = "VIBEPAPER_"
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
