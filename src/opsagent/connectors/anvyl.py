from __future__ import annotations

from opsagent.http import ApiSession
from opsagent.settings import Settings


class AnvylClient:
    """Sage Supply Chain Intelligence, still documented as the Anvyl API.

    GET /api/v1/teams/{team_id}/purchase_orders
    Auth: the API key in the Authorization header, without the word Bearer.
    Pagination: page and per_page, counts in X-Page / X-Per-Page / X-Total-Pages.
    Money on order items is unit_price_micros (euros * 1_000_000).
    sku and quantity_received are inlined in this fixture. Live, sku comes from
    the part record and received quantity from shipments.
    """

    def __init__(self, session: ApiSession, settings: Settings):
        self.session = session
        self.settings = settings

    def list_purchase_orders(self) -> tuple[list[dict], int]:
        page = 1
        rows: list[dict] = []
        pages = 0
        total_pages = 1
        while page <= total_pages:
            response = self.session.send(
                "GET",
                f"/api/v1/teams/{self.settings.anvyl_team_id}/purchase_orders",
                params={"page": page, "per_page": 2},
            )
            pages += 1
            rows.extend(response.json()["purchase_orders"])
            total_pages = int(response.headers["X-Total-Pages"])
            page += 1
        return rows, pages
