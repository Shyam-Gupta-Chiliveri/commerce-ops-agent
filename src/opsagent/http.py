from __future__ import annotations

import time

import httpx


class ApiSession:
    """HTTP session that retries 429 and otherwise raises.

    Each vendor client keeps its own pagination, because Shopify, Zendesk,
    Klaviyo, Anvyl and Sage do not share one paging style.
    """

    def __init__(self, client: httpx.Client, base_url: str, headers: dict[str, str] | None = None, auth=None):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.auth = auth

    def send(self, method: str, url: str, *, params=None, headers=None) -> httpx.Response:
        if not url.startswith("http"):
            url = self.base_url + url
        merged = {**self.headers, **(headers or {})}
        for attempt in range(3):
            response = self.client.request(method, url, params=params, headers=merged, auth=self.auth)
            if response.status_code == 429 and attempt < 2:
                time.sleep(float(response.headers.get("Retry-After", "0")))
                continue
            response.raise_for_status()
            return response
        raise RuntimeError(f"{method} {url} failed after retries")
