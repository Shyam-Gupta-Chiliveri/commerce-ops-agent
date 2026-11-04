from __future__ import annotations

import httpx

from opsagent.connectors.anvyl import AnvylClient
from opsagent.connectors.klaviyo import KlaviyoClient
from opsagent.connectors.sage import SageClient
from opsagent.connectors.shopify import ShopifyClient
from opsagent.connectors.zendesk import ZendeskClient
from opsagent.http import ApiSession
from opsagent.settings import Settings


def zendesk_auth(settings: Settings) -> httpx.BasicAuth:
    return httpx.BasicAuth(f"{settings.zendesk_email}/token", settings.zendesk_api_token)


def build_clients(http: httpx.Client, settings: Settings, base_url: str = "http://mock"):
    shopify = ShopifyClient(ApiSession(http, base_url, {"X-Shopify-Access-Token": settings.shopify_token}))
    zendesk = ZendeskClient(ApiSession(http, base_url, auth=zendesk_auth(settings)))
    klaviyo = KlaviyoClient(
        ApiSession(
            http,
            base_url,
            {
                "Authorization": f"Klaviyo-API-Key {settings.klaviyo_key}",
                "revision": settings.klaviyo_revision,
                "accept": "application/json",
            },
        )
    )
    anvyl = AnvylClient(ApiSession(http, base_url, {"Authorization": settings.anvyl_key}), settings)
    sage = SageClient(
        ApiSession(
            http,
            base_url,
            {
                "Authorization": f"Bearer {settings.sage_token}",
                "X-Business": settings.sage_business,
            },
        )
    )
    return shopify, zendesk, klaviyo, anvyl, sage
