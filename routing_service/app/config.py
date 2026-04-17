from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str
    gemini_model: str = "gemini-2.0-flash"

    # Optional: outbound confirmation calls via Twilio (https URL reachable from the internet, e.g. ngrok).
    public_base_url: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
