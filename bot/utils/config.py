import os
from dataclasses import dataclass
from typing import List

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BillingConfig:
    enabled: bool
    monthly_price_usd: float
    trial_notes: int
    payment_url: str


@dataclass
class FeaturesConfig:
    weekly_digest: bool
    vector_search: bool
    max_voice_duration_sec: int


@dataclass
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    anthropic_api_key: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_id: str
    database_url: str
    webhook_host: str
    webhook_path: str
    web_port: int
    payment_hmac_secret: str
    admins: List[int]

    billing: BillingConfig
    features: FeaturesConfig


def _load() -> Settings:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    billing_raw = cfg.get("billing", {})
    features_raw = cfg.get("features", {})

    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        stripe_secret_key=os.environ.get("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        stripe_price_id=os.environ.get("STRIPE_PRICE_ID", ""),
        database_url=os.environ["DATABASE_URL"],
        webhook_host=os.environ.get("WEBHOOK_HOST", ""),
        webhook_path=os.environ.get("WEBHOOK_PATH", "/webhook"),
        web_port=int(os.environ.get("WEB_PORT", "8080")),
        payment_hmac_secret=os.environ.get("PAYMENT_HMAC_SECRET", "change-me"),
        admins=[int(uid) for uid in cfg.get("admins", [])],
        billing=BillingConfig(
            enabled=billing_raw.get("enabled", True),
            monthly_price_usd=billing_raw.get("monthly_price_usd", 5.00),
            trial_notes=billing_raw.get("trial_notes", 10),
            payment_url=billing_raw.get("payment_url", ""),
        ),
        features=FeaturesConfig(
            weekly_digest=features_raw.get("weekly_digest", True),
            vector_search=features_raw.get("vector_search", True),
            max_voice_duration_sec=features_raw.get("max_voice_duration_sec", 300),
        ),
    )


settings = _load()
