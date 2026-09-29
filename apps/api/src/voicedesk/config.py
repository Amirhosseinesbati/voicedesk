from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./voicedesk-demo.db"
    app_secret_key: str = "local-demo-only-change-before-deployment"
    app_mode: str = "demo"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cookie_secure: bool = False
    cookie_domain: str | None = None
    demo_data_path: str | None = None
    demo_data_size: str = "full"
    demo_seed: int = 20260927
    demo_reference_date: str = "2026-09-27"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_stt_model: str = "gpt-live-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "coral"
    calendar_provider: str = "local"
    google_calendar_id: str | None = None
    google_service_account_json: str | None = None
    retention_days: int = 90
    audio_retention_enabled: bool = False

    @property
    def is_demo(self) -> bool:
        return self.app_mode == "demo"

    @property
    def api_root(self) -> Path:
        return Path(__file__).resolve().parents[4]


@lru_cache
def get_settings() -> Settings:
    return Settings()
