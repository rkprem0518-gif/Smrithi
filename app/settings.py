"""Application settings, read from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LiveConfigError(RuntimeError):
    """Raised when live mode is requested without the keys it needs."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_env: str = "development"
    demo_mode: bool = True
    public_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./smriti.db"
    secret_salt: str = "change-me"
    admin_review_token: str = "change-me"

    # Bolna
    bolna_api_base: str = "https://api.bolna.ai"
    bolna_api_key: str = ""
    bolna_agent_id: str = ""
    bolna_from_number: str = ""
    bolna_webhook_token: str = "change-me"

    # Optional ASR fallback
    asr_provider: Literal["none", "sarvam", "deepgram"] = "none"
    sarvam_api_key: str = ""
    deepgram_api_key: str = ""

    # Safety limits
    max_calls_per_ip_per_day: int = 3
    max_call_minutes: int = 8
    helpline_text: str = ""
    max_calls_per_number_per_day: int = 2  # same phone number, any IP
    max_calls_per_day: int = 60  # whole deployment, live mode only

    # Internal knobs (not in .env.example; handy for tests)
    poll_interval_seconds: float = 10.0
    poll_give_up_minutes: float = 15.0
    bolna_timeout_seconds: float = 15.0
    bolna_retry_backoff_seconds: float = 0.5
    demo_call_step_seconds: float = 2.0

    @field_validator("*", mode="before")
    @classmethod
    def _strip_inline_comment(cls, value: Any) -> Any:
        # python-dotenv reads `KEY=   # comment` as the value "# comment".
        if isinstance(value, str):
            stripped = value.strip()
            return "" if stripped.startswith("#") else stripped
        return value

    @property
    def bolna_configured(self) -> bool:
        return bool(self.bolna_api_key and self.bolna_agent_id)

    @property
    def webhook_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}/api/bolna/webhook?token={self.bolna_webhook_token}"

    @property
    def webhook_reachable(self) -> bool:
        """Bolna can only reach a public https URL."""
        url = self.public_base_url.lower()
        return url.startswith("https://") and "localhost" not in url and "127.0.0.1" not in url

    def missing_live_keys(self) -> list[str]:
        missing = []
        if not self.bolna_api_key:
            missing.append("BOLNA_API_KEY")
        if not self.bolna_agent_id:
            missing.append("BOLNA_AGENT_ID")
        return missing

    def default_secrets(self) -> list[str]:
        defaults = {"SECRET_SALT": self.secret_salt, "ADMIN_REVIEW_TOKEN": self.admin_review_token,
                    "BOLNA_WEBHOOK_TOKEN": self.bolna_webhook_token}
        return [k for k, v in defaults.items() if v in ("", "change-me")]

    def require_live(self) -> None:
        missing = self.missing_live_keys()
        if missing:
            raise LiveConfigError(
                "DEMO_MODE=0 (live mode) but these are not set in .env: "
                + ", ".join(missing)
                + ". Run scripts/create_agent.py to get BOLNA_AGENT_ID, "
                "or set DEMO_MODE=1 to run offline."
            )
        weak = self.default_secrets()
        if weak:
            # Real transcripts and phone hashes are at stake: never run live on the example secrets.
            raise LiveConfigError(
                "DEMO_MODE=0 (live mode) but these still have the example value 'change-me': "
                + ", ".join(weak)
                + '. Set each to a long random string: python -c "import secrets; print(secrets.token_urlsafe(24))"'
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
