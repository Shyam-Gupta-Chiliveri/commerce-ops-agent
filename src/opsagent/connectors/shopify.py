from __future__ import annotations

from opsagent.http import ApiSession


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


class ShopifyClient:
    """Shopify Admin REST, 2024-10.

    Auth header: X-Shopify-Access-Token.
    List endpoints page with an opaque cursor in the Link header. The client
    sends that URL back untouched and does not parse page_info.
    """

    def __init__(self, session: ApiSession, api_version: str = "2024-10"):
        self.session = session
        self.api_version = api_version

    def _headers(self) -> dict[str, str]:
        return {}

    def list_orders(self) -> tuple[list[dict], int]:
        url: str | None = f"/admin/api/{self.api_version}/orders.json?status=any&limit=2"
        rows: list[dict] = []
        pages = 0
        while url:
            response = self.session.send("GET", url)
            pages += 1
            rows.extend(response.json()["orders"])
            url = _next_link(response.headers.get("Link"))
        return rows, pages

    def list_variants(self) -> tuple[list[dict], int]:
        url: str | None = f"/admin/api/{self.api_version}/variants.json?limit=2"
        rows: list[dict] = []
        pages = 0
        while url:
            response = self.session.send("GET", url)
            pages += 1
            rows.extend(response.json()["variants"])
            url = _next_link(response.headers.get("Link"))
        return rows, pages

    def list_transactions(self, order_id: int) -> list[dict]:
        response = self.session.send("GET", f"/admin/api/{self.api_version}/orders/{order_id}/transactions.json")
        return response.json()["transactions"]
