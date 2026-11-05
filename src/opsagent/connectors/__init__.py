from __future__ import annotations

import httpx

from opsagent.connectors.anvyl import AnvylClient
from opsagent.connectors.klaviyo import KlaviyoClient
from opsagent.connectors.sage import SageClient
from opsagent.connectors.shopify import ShopifyClient
from opsagent.connectors.zendesk import ZendeskClient
from opsagent.http import ApiSession
from opsagent.settings import Settings, klaviyo_base, sage_base, shopify_base, zendesk_base


def zendesk_auth(settings: Settings) -> httpx.BasicAuth:
    return httpx.BasicAuth(f"{settings.zendesk_email}/token", settings.zendesk_api_token)


def zendesk_access_token(settings: Settings, live_http: httpx.Client) -> str:
    """Exchange a confidential OAuth client for a Support API bearer token."""
    response = live_http.post(
        f"{zendesk_base(settings)}/oauth/tokens",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.zendesk_client_id,
            "client_secret": settings.zendesk_client_secret,
            "scope": "tickets:read users:read",
        },
    )
    if response.status_code == 400:
        response = live_http.post(
            f"{zendesk_base(settings)}/oauth/tokens",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.zendesk_client_id,
                "client_secret": settings.zendesk_client_secret,
                "scope": "read",
            },
        )
    response.raise_for_status()
    return response.json()["access_token"]


def shopify_access_token(settings: Settings, live_http: httpx.Client) -> str:
    """Use a stored token, or exchange a Dev Dashboard app secret for a short-lived one."""
    if settings.shopify_token not in ("", "shpat_demo"):
        return settings.shopify_token
    if not (settings.shopify_client_id and settings.shopify_client_secret):
        return settings.shopify_token
    response = live_http.post(
        f"{shopify_base(settings)}/admin/oauth/access_token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.shopify_client_id,
            "client_secret": settings.shopify_client_secret,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def build_clients(http: httpx.Client, settings: Settings, live_http: httpx.Client | None = None):
    live_http = live_http or http

    def session(base: str, headers: dict[str, str] | None = None, auth=None) -> ApiSession:
        client = live_http if base.startswith("https://") else http
        return ApiSession(client, base, headers, auth)

    shop_base = shopify_base(settings)
    zd_base = zendesk_base(settings)
    kl_base = klaviyo_base(settings)
    sg_base = sage_base(settings)
    revision = settings.klaviyo_revision
    if kl_base.startswith("https://") and revision == "2025-04-15":
        revision = "2026-10-15"
    shop_version = "2026-10" if shop_base.startswith("https://") else "2024-10"
    shop_token = shopify_access_token(settings, live_http) if shop_base.startswith("https://") else settings.shopify_token

    shopify = ShopifyClient(session(shop_base, {"X-Shopify-Access-Token": shop_token}), shop_version)
    if zd_base.startswith("https://") and settings.zendesk_client_id and settings.zendesk_client_secret:
        zendesk = ZendeskClient(
            session(zd_base, {"Authorization": f"Bearer {zendesk_access_token(settings, live_http)}"})
        )
    else:
        zendesk = ZendeskClient(session(zd_base, auth=zendesk_auth(settings)))
    klaviyo = KlaviyoClient(
        session(
            kl_base,
            {
                "Authorization": f"Klaviyo-API-Key {settings.klaviyo_key}",
                "revision": revision,
                "accept": "application/json",
            },
        )
    )
    anvyl = AnvylClient(session("http://mock", {"Authorization": settings.anvyl_key}), settings)
    sage = SageClient(
        session(
            sg_base,
            {
                "Authorization": f"Bearer {settings.sage_token}",
                "X-Business": settings.sage_business,
            },
        )
    )
    return shopify, zendesk, klaviyo, anvyl, sage
