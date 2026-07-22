from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    pb_url: str = "http://pocketbase:8090"
    pb_superuser_email: str = "admin@example.com"
    pb_superuser_password: str = ""
    unified_data_dir: str = "data/unified/private"
    # Empty secret disables the Turnstile check (dev / honeypot-only fallback).
    turnstile_secret: str = ""
    max_upload_bytes: int = 10 * 1024 * 1024
    systems_per_ip_per_hour: int = 3
    uploads_per_ip_per_minute: int = 20
    uploads_per_system_per_day: int = 60
    judge_enabled: bool = False
    openrouter_api_key: str = ""

    model_config = {"env_prefix": "WMT26_"}


settings = Settings()
