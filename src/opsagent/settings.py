"""Fixture credentials and the frozen business clock.

The tokens below are for the local fixture server. They are not secrets.
Production reads the same fields from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    shopify_token: str = "shpat_demo"
    shopify_webhook_secret: str = "whsec_demo"
    zendesk_email: str = "agent@harborhouse.example"
    zendesk_api_token: str = "zd_demo"
    klaviyo_key: str = "klaviyo_demo"
    klaviyo_revision: str = "2025-04-15"
    anvyl_key: str = "anvyl_demo"
    anvyl_team_id: str = "555"
    sage_token: str = "sage_demo"
    sage_business: str = "biz_demo"
    as_of: str = "2026-11-04"
    delay_offer_after_days: int = 7
    delay_discount_pct: int = 15
    return_window_days: int = 30
    page_size: int = 2


def load_settings() -> Settings:
    base = Settings()
    return Settings(
        shopify_token=os.getenv("SHOPIFY_TOKEN", base.shopify_token),
        shopify_webhook_secret=os.getenv("SHOPIFY_WEBHOOK_SECRET", base.shopify_webhook_secret),
        zendesk_email=os.getenv("ZENDESK_EMAIL", base.zendesk_email),
        zendesk_api_token=os.getenv("ZENDESK_API_TOKEN", base.zendesk_api_token),
        klaviyo_key=os.getenv("KLAVIYO_API_KEY", base.klaviyo_key),
        klaviyo_revision=os.getenv("KLAVIYO_REVISION", base.klaviyo_revision),
        anvyl_key=os.getenv("ANVYL_API_KEY", base.anvyl_key),
        anvyl_team_id=os.getenv("ANVYL_TEAM_ID", base.anvyl_team_id),
        sage_token=os.getenv("SAGE_TOKEN", base.sage_token),
        sage_business=os.getenv("SAGE_BUSINESS", base.sage_business),
        as_of=os.getenv("OPSAGENT_AS_OF", base.as_of),
    )
