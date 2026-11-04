from __future__ import annotations

from opsagent.http import ApiSession


class ZendeskClient:
    """Zendesk Support REST, /api/v2.

    Auth is Basic: `{email}/token:{api_token}`.
    Collections return next_page until it is null.
    Resolvia, which SNOCKS uses as the helpdesk, would be a second client
    writing the same ticket tables. This client does not pretend to be Resolvia.
    """

    def __init__(self, session: ApiSession):
        self.session = session

    def list_tickets(self) -> tuple[list[dict], int]:
        url: str | None = "/api/v2/tickets.json?per_page=2"
        rows: list[dict] = []
        pages = 0
        while url:
            response = self.session.send("GET", url)
            pages += 1
            body = response.json()
            rows.extend(body["tickets"])
            url = body.get("next_page")
        return rows, pages

    def list_users(self) -> list[dict]:
        url: str | None = "/api/v2/users.json?per_page=2"
        rows: list[dict] = []
        while url:
            response = self.session.send("GET", url)
            body = response.json()
            rows.extend(body["users"])
            url = body.get("next_page")
        return rows

    def list_comments(self, ticket_id: int) -> list[dict]:
        response = self.session.send("GET", f"/api/v2/tickets/{ticket_id}/comments.json")
        return response.json()["comments"]
