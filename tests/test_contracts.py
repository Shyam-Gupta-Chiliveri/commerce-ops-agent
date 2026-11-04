from __future__ import annotations

import httpx

from opsagent.http import ApiSession
from opsagent.rules import review_bill
from opsagent.security import shopify_hmac, shopify_hmac_valid


def test_retries_429():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = ApiSession(client, "http://example").send("GET", "/ping")
    assert response.json()["ok"] is True
    assert calls["n"] == 2


def test_shopify_hmac_roundtrip():
    body = b'{"id":1}'
    given = shopify_hmac("whsec_demo", body)
    assert shopify_hmac_valid("whsec_demo", body, given)
    assert not shopify_hmac_valid("whsec_demo", body, "nope")


def test_webhook_rejects_bad_signature(http):
    response = http.post("/webhooks/shopify/orders", content=b"{}")
    assert response.status_code == 401
    good = shopify_hmac("whsec_demo", b"{}")
    response = http.post("/webhooks/shopify/orders", content=b"{}", headers={"X-Shopify-Hmac-Sha256": good})
    assert response.status_code == 200


def test_missing_token_is_401(http):
    response = http.get("/admin/api/2024-10/orders.json")
    assert response.status_code == 401


def test_bill_rule_flags_quantity_and_value():
    decision, issues = review_bill(ordered_qty=400, billed_qty=480, ordered_net=4800, billed_net=5760)
    assert decision == "INVESTIGATE"
    assert issues == ["QTY_OVER", "OVER_PO_VALUE"]


def test_bill_rule_approves_a_match():
    decision, issues = review_bill(ordered_qty=1000, billed_qty=1000, ordered_net=2500, billed_net=2500)
    assert decision == "APPROVE"
    assert issues == []
