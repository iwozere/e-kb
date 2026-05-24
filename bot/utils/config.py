import os
from dataclasses import dataclass, field
from typing import List

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class FeaturesConfig:
    vector_search: bool = True
    daily_digest: bool = True
    weekly_digest_push: bool = True
    max_voice_duration_sec: int = 300
    max_text_length_chars: int = 4000


@dataclass
class DigestConfig:
    daily_time: str = "21:00"
    weekly_day: str = "monday"
    weekly_time: str = "08:00"
    max_entries_per_summary: int = 50


@dataclass
class WhisperConfig:
    use_local: bool = False
    local_model: str = "small"


@dataclass
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    anthropic_api_key: str
    database_url: str
    webhook_host: str = ""
    webhook_path: str = "/webhook"
    web_port: int = 8080
    admins: List[int] = field(default_factory=list)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    digest: DigestConfig = field(default_factory=DigestConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)


def _load() -> Settings:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    features_raw = cfg.get("features", {})
    digest_raw = cfg.get("digest", {})
    whisper_raw = cfg.get("whisper", {})

    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        database_url=os.environ["DATABASE_URL"],
        webhook_host=os.environ.get("WEBHOOK_HOST", ""),
        webhook_path=os.environ.get("WEBHOOK_PATH", "/webhook"),
        web_port=int(os.environ.get("WEB_PORT", "8080")),
        admins=[int(uid) for uid in cfg.get("admins", [])],
        features=FeaturesConfig(
            vector_search=features_raw.get("vector_search", True),
            daily_digest=features_raw.get("daily_digest", True),
            weekly_digest_push=features_raw.get("weekly_digest_push", True),
            max_voice_duration_sec=features_raw.get("max_voice_duration_sec", 300),
            max_text_length_chars=features_raw.get("max_text_length_chars", 4000),
        ),
        digest=DigestConfig(
            daily_time=digest_raw.get("daily_time", "21:00"),
            weekly_day=digest_raw.get("weekly_day", "monday"),
            weekly_time=digest_raw.get("weekly_time", "08:00"),
            max_entries_per_summary=digest_raw.get("max_entries_per_summary", 50),
        ),
        whisper=WhisperConfig(
            use_local=whisper_raw.get("use_local", False),
            local_model=whisper_raw.get("local_model", "small"),
        ),
    )


settings = _load()
