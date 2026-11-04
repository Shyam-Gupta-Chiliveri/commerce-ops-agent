from __future__ import annotations

import math

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from opsagent.fixture_io import load_json
from opsagent.security import shopify_hmac_valid
from opsagent.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    shopify = load_json("shopify.json")
    zendesk = load_json("zendesk.json")
    klaviyo = load_json("klaviyo.json")
    anvyl = load_json("anvyl.json")
    sage = load_json("sage.json")
    app = FastAPI(title="Harbor House fixture APIs", redirect_slashes=False)

    def require_shopify(request: Request) -> None:
        if request.headers.get("x-shopify-access-token") != settings.shopify_token:
            raise HTTPException(status_code=401, detail="shopify token")

    def require_zendesk(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Basic "):
            raise HTTPException(status_code=401, detail="zendesk auth")
        import base64

        try:
            raw = base64.b64decode(header.split(" ", 1)[1]).decode()
        except Exception as exc:
            raise HTTPException(status_code=401, detail="zendesk auth") from exc
        expected = f"{settings.zendesk_email}/token:{settings.zendesk_api_token}"
        if raw != expected:
            raise HTTPException(status_code=401, detail="zendesk auth")

    def require_klaviyo(request: Request) -> None:
        if request.headers.get("authorization") != f"Klaviyo-API-Key {settings.klaviyo_key}":
            raise HTTPException(status_code=401, detail="klaviyo key")
        if request.headers.get("revision") != settings.klaviyo_revision:
            raise HTTPException(status_code=400, detail="revision header required")

    def require_anvyl(request: Request) -> None:
        if request.headers.get("authorization") != settings.anvyl_key:
            raise HTTPException(status_code=401, detail="anvyl key")

    def require_sage(request: Request) -> None:
        if request.headers.get("authorization") != f"Bearer {settings.sage_token}":
            raise HTTPException(status_code=401, detail="sage token")
        if request.headers.get("x-business") != settings.sage_business:
            raise HTTPException(status_code=400, detail="X-Business required")

    def paged(items: list, offset: int, limit: int):
        piece = items[offset : offset + limit]
        nxt = offset + limit if offset + limit < len(items) else None
        return piece, nxt

    @app.get("/health")
    def health():
        return {"ok": True, "as_of": settings.as_of}

    @app.post("/webhooks/shopify/orders")
    async def shopify_webhook(request: Request):
        body = await request.body()
        given = request.headers.get("x-shopify-hmac-sha256", "")
        if not shopify_hmac_valid(settings.shopify_webhook_secret, body, given):
            raise HTTPException(status_code=401, detail="bad hmac")
        return {"accepted": True}

    @app.get("/admin/api/2024-10/orders.json")
    def shopify_orders(request: Request):
        require_shopify(request)
        offset = int(request.query_params.get("page_info", "0"))
        limit = int(request.query_params.get("limit", "2"))
        name = request.query_params.get("name")
        items = shopify["orders"]
        if name:
            items = [order for order in items if order["name"] == name or order["name"] == f"#{name}"]
        piece, nxt = paged(items, offset, limit)
        response = JSONResponse({"orders": piece})
        if nxt is not None:
            url = request.url.include_query_params(page_info=str(nxt), limit=str(limit))
            response.headers["Link"] = f'<{url}>; rel="next"'
        return response

    @app.get("/admin/api/2024-10/variants.json")
    def shopify_variants(request: Request):
        require_shopify(request)
        offset = int(request.query_params.get("page_info", "0"))
        limit = int(request.query_params.get("limit", "2"))
        piece, nxt = paged(shopify["variants"], offset, limit)
        response = JSONResponse({"variants": piece})
        if nxt is not None:
            url = request.url.include_query_params(page_info=str(nxt), limit=str(limit))
            response.headers["Link"] = f'<{url}>; rel="next"'
        return response

    @app.get("/admin/api/2024-10/orders/{order_id}/transactions.json")
    def shopify_transactions(order_id: int, request: Request):
        require_shopify(request)
        rows = shopify["transactions"].get(str(order_id), [])
        return {"transactions": rows}

    @app.get("/api/v2/tickets.json")
    def zendesk_tickets(request: Request):
        require_zendesk(request)
        return _zendesk_page(request, zendesk["tickets"], "tickets")

    @app.get("/api/v2/users.json")
    def zendesk_users(request: Request):
        require_zendesk(request)
        return _zendesk_page(request, zendesk["users"], "users")

    @app.get("/api/v2/tickets/{ticket_id}/comments.json")
    def zendesk_comments(ticket_id: int, request: Request):
        require_zendesk(request)
        return {"comments": zendesk["comments"].get(str(ticket_id), [])}

    @app.get("/api/events")
    def klaviyo_events(request: Request):
        require_klaviyo(request)
        offset = int(request.query_params.get("cursor", "0"))
        limit = int(request.query_params.get("page_size", "2"))
        piece, nxt = paged(klaviyo["events"], offset, limit)
        metrics = {item["id"]: item for item in klaviyo["metrics"]}
        profiles = {item["id"]: item for item in klaviyo["profiles"]}
        included = []
        seen = set()
        for event in piece:
            metric_id = event["relationships"]["metric"]["data"]["id"]
            profile_id = event["relationships"]["profile"]["data"]["id"]
            for key, item in (("metric", metrics[metric_id]), ("profile", profiles[profile_id])):
                marker = (key, item["id"])
                if marker not in seen:
                    seen.add(marker)
                    included.append(item)
        links = {"next": None}
        if nxt is not None:
            links["next"] = str(request.url.include_query_params(cursor=str(nxt), page_size=str(limit)))
        return {"data": piece, "included": included, "links": links}

    @app.get("/api/v1/teams/{team_id}/purchase_orders")
    def anvyl_purchase_orders(team_id: str, request: Request):
        require_anvyl(request)
        if team_id != settings.anvyl_team_id:
            raise HTTPException(status_code=404, detail="unknown team")
        page = int(request.query_params.get("page", "1"))
        per_page = int(request.query_params.get("per_page", "2"))
        items = anvyl["purchase_orders"]
        total = len(items)
        total_pages = max(1, math.ceil(total / per_page))
        start = (page - 1) * per_page
        piece = items[start : start + per_page]
        response = JSONResponse({"purchase_orders": piece})
        response.headers["X-Page"] = str(page)
        response.headers["X-Per-Page"] = str(per_page)
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Total-Pages"] = str(total_pages)
        return response

    @app.get("/v3.1/purchase_invoices")
    def sage_purchase_invoices(request: Request):
        require_sage(request)
        page = int(request.query_params.get("page", "1"))
        per_page = int(request.query_params.get("items_per_page", "2"))
        items = sage["purchase_invoices"]
        start = (page - 1) * per_page
        piece = items[start : start + per_page]
        nxt = None
        if start + per_page < len(items):
            nxt = str(request.url.include_query_params(page=str(page + 1), items_per_page=str(per_page)))
        return {"$page": page, "$next": nxt, "purchase_invoices": piece}

    return app


def _zendesk_page(request: Request, items: list, key: str) -> dict:
    page = int(request.query_params.get("page", "1"))
    per_page = int(request.query_params.get("per_page", "2"))
    start = (page - 1) * per_page
    piece = items[start : start + per_page]
    nxt = None
    if start + per_page < len(items):
        nxt = str(request.url.include_query_params(page=str(page + 1), per_page=str(per_page)))
    return {key: piece, "count": len(items), "next_page": nxt}
