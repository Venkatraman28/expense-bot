from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram & App Settings
    TELEGRAM_BOT_TOKEN: str
    ALLOWED_CHAT_IDS: set[int]
    DB_PATH: str = "data/expense_bot.db"
    DEFAULT_CURRENCY: str = "INR"

    # Primary Provider: NVIDIA
    NVIDIA_API_KEY: str | None = None
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "meta/llama-3.1-70b-instruct"
    NVIDIA_AUDIO_MODEL: str = ""
    NVIDIA_VISION_MODEL: str = ""
    NVIDIA_TIMEOUT: int = 600

    # Secondary / Fallback Provider: Groq
    GROQ_API_KEY: str | None = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_AUDIO_MODEL: str = "whisper-large-v3-turbo"
    GROQ_VISION_MODEL: str = ""
    GROQ_TIMEOUT: int = 300

    # Single toggle switch: "groq" or "nvidia"
    ACTIVE_LLM_PROVIDER: Literal["groq", "nvidia"] = "groq"
    ACTIVE_VISION_LLM_PROVIDER: Literal["groq", "nvidia"] = "nvidia"

    # Model parameters
    TEMPERATURE: float = 0
    REASONING_EFFORT: Literal["low", "medium", "high"] | None = "low"

    @field_validator("ALLOWED_CHAT_IDS", mode="before")
    @classmethod
    def parse_allowed_chat_ids(cls, v: str | int | set[int]) -> set[int]:
        if isinstance(v, (set, list)):
            return {int(x) for x in v}
        return {int(x.strip()) for x in str(v).split(",") if x.strip()}


settings = Settings()