from __future__ import annotations

from opsagent.http import ApiSession


class SageClient:
    """Sage Business Cloud Accounting, purchase invoices, v3.1.

    GET /v3.1/purchase_invoices
    Auth: OAuth Bearer token plus the X-Business header.
    Pagination: the body field `$next` is empty on the last page.
    This fixture is a reduced purchase_invoices payload. The pay-or-investigate
    decision is not a Sage status; rules.py adds it after the load.
    """

    def __init__(self, session: ApiSession):
        self.session = session

    def list_purchase_invoices(self) -> tuple[list[dict], int]:
        page = 1
        rows: list[dict] = []
        pages = 0
        while True:
            response = self.session.send(
                "GET",
                "/v3.1/purchase_invoices",
                params={"page": page, "items_per_page": 2},
            )
            pages += 1
            body = response.json()
            rows.extend(body["purchase_invoices"])
            if not body.get("$next"):
                break
            page += 1
        return rows, pages
