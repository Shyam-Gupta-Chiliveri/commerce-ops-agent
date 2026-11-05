"""Fixture credentials and the frozen business clock.

The tokens below are for the local fixture server. They are not secrets.
Production reads the same fields from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from opsagent.paths import PROJECT_ROOT


@dataclass(frozen=True)
class Settings:
    shopify_token: str = "shpat_demo"
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_shop: str = ""
    shopify_webhook_secret: str = "whsec_demo"
    zendesk_email: str = "agent@harborhouse.example"
    zendesk_api_token: str = "zd_demo"
    zendesk_client_id: str = ""
    zendesk_client_secret: str = ""
    zendesk_subdomain: str = ""
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


def _load_dotenv() -> None:
    path = PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _host(value: str, suffix: str) -> str:
    host = value.strip().removeprefix("https://").removeprefix("http://").strip("/")
    if host.endswith(suffix):
        return host
    return f"{host}{suffix}"


def shopify_base(settings: Settings) -> str:
    shop = settings.shopify_shop.strip()
    has_token = settings.shopify_token not in ("", "shpat_demo")
    has_app = bool(settings.shopify_client_id.strip() and settings.shopify_client_secret.strip())
    if not shop or not (has_token or has_app):
        return "http://mock"
    return f"https://{_host(shop, '.myshopify.com')}"


def zendesk_base(settings: Settings) -> str:
    sub = settings.zendesk_subdomain.strip()
    has_token = settings.zendesk_api_token not in ("", "zd_demo")
    has_oauth = bool(settings.zendesk_client_id.strip() and settings.zendesk_client_secret.strip())
    if not sub or not (has_token or has_oauth):
        return "http://mock"
    return f"https://{_host(sub, '.zendesk.com')}"


def klaviyo_base(settings: Settings) -> str:
    if settings.klaviyo_key in ("", "klaviyo_demo"):
        return "http://mock"
    return "https://a.klaviyo.com"


def sage_base(settings: Settings) -> str:
    if settings.sage_token in ("", "sage_demo") or settings.sage_business in ("", "biz_demo"):
        return "http://mock"
    return "https://api.accounting.sage.com"


_ACCOUNT_WORDS = {
    "shopify": ("Shopify", "shopify_orders", ("order", "orders"), ("Bestellung", "Bestellungen")),
    "zendesk": ("Zendesk", "zendesk_tickets", ("ticket", "tickets"), ("Ticket", "Tickets")),
    "klaviyo": ("Klaviyo", "klaviyo_events", ("event", "events"), ("Ereignis", "Ereignisse")),
    "sage": ("Sage", "sage_bills", ("bill", "bills"), ("Rechnung", "Rechnungen")),
}


def _account_piece(name: str, host: str, accounts: dict[str, int] | None, lang: str) -> str:
    label, key, english, german = _ACCOUNT_WORDS[name]
    count = None if accounts is None else accounts.get(key)
    if count is None:
        return f"{label} {host} stays connected" if lang == "en" else f"{label} {host} bleibt verbunden"
    word = (english if lang == "en" else german)[0 if count == 1 else 1]
    if lang == "en":
        return f"{label} {host} stays connected, {count} {word} in the account"
    return f"{label} {host} bleibt verbunden, {count} {word} im Konto"


def origins(settings: Settings, accounts: dict[str, int] | None = None) -> dict[str, object]:
    hosts = {
        "shopify": shopify_base(settings),
        "zendesk": zendesk_base(settings),
        "klaviyo": klaviyo_base(settings),
        "anvyl": "http://mock",
        "sage": sage_base(settings),
    }
    live = [name for name in ("shopify", "zendesk", "klaviyo", "sage") if str(hosts[name]).startswith("https://")]
    if not live:
        text_en = "These counts were read from the local sample, not from a signed-in account."
        text_de = "Diese Zahlen stammen aus der lokalen Beispielkopie, nicht aus einem angemeldeten Konto."
    else:
        pieces_en = ". ".join(_account_piece(name, str(hosts[name]), accounts, "en") for name in live)
        pieces_de = ". ".join(_account_piece(name, str(hosts[name]), accounts, "de") for name in live)
        sage_en = "" if "sage" in live else " Sage stays on the example bills."
        sage_de = "" if "sage" in live else " Sage bleibt bei den Beispielrechnungen."
        text_en = f"The inbox keeps the examples. {pieces_en}.{sage_en}"
        text_de = f"Der Posteingang behält die Beispiele. {pieces_de}.{sage_de}"
    return {"hosts": hosts, "en": text_en, "de": text_de, "accounts": accounts or {}}


def load_settings() -> Settings:
    _load_dotenv()
    base = Settings()
    return Settings(
        shopify_token=os.getenv("SHOPIFY_TOKEN", base.shopify_token),
        shopify_client_id=os.getenv("SHOPIFY_CLIENT_ID", base.shopify_client_id),
        shopify_client_secret=os.getenv("SHOPIFY_CLIENT_SECRET", base.shopify_client_secret),
        shopify_shop=os.getenv("SHOPIFY_SHOP", base.shopify_shop),
        shopify_webhook_secret=os.getenv("SHOPIFY_WEBHOOK_SECRET", base.shopify_webhook_secret),
        zendesk_email=os.getenv("ZENDESK_EMAIL", base.zendesk_email),
        zendesk_api_token=os.getenv("ZENDESK_API_TOKEN", base.zendesk_api_token),
        zendesk_client_id=os.getenv("ZENDESK_CLIENT_ID", base.zendesk_client_id),
        zendesk_client_secret=os.getenv("ZENDESK_CLIENT_SECRET", base.zendesk_client_secret),
        zendesk_subdomain=os.getenv("ZENDESK_SUBDOMAIN", base.zendesk_subdomain),
        klaviyo_key=os.getenv("KLAVIYO_API_KEY", base.klaviyo_key),
        klaviyo_revision=os.getenv("KLAVIYO_REVISION", base.klaviyo_revision),
        anvyl_key=os.getenv("ANVYL_API_KEY", base.anvyl_key),
        anvyl_team_id=os.getenv("ANVYL_TEAM_ID", base.anvyl_team_id),
        sage_token=os.getenv("SAGE_TOKEN", base.sage_token),
        sage_business=os.getenv("SAGE_BUSINESS", base.sage_business),
        as_of=os.getenv("OPSAGENT_AS_OF", base.as_of),
    )
