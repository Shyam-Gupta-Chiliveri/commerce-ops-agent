from __future__ import annotations

from opsagent.http import ApiSession


class KlaviyoClient:
    """Klaviyo Events API.

    Requires Authorization `Klaviyo-API-Key ...` and a `revision` header.
    Collections page with links.next. The revision date must be one Klaviyo
    currently publishes; bump KLAVIYO_REVISION when you point this at a live account.
    """

    def __init__(self, session: ApiSession):
        self.session = session

    def list_events(self) -> tuple[list[dict], int]:
        query = "page_size=2"
        if "klaviyo.com" in self.session.base_url:
            query = "include=metric,profile&page_size=2"
        url: str | None = f"/api/events?{query}"
        rows: list[dict] = []
        pages = 0
        while url:
            response = self.session.send("GET", url)
            pages += 1
            body = response.json()
            included = {(item["type"], item["id"]): item for item in body.get("included", [])}
            for event in body["data"]:
                metric_id = event["relationships"]["metric"]["data"]["id"]
                profile_id = event["relationships"]["profile"]["data"]["id"]
                metric = included[("metric", metric_id)]
                profile = included[("profile", profile_id)]
                rows.append(
                    {
                        "id": event["id"],
                        "datetime": event["attributes"]["datetime"],
                        "properties": event["attributes"].get("event_properties") or {},
                        "metric": metric["attributes"]["name"],
                        "email": profile["attributes"]["email"],
                    }
                )
            url = (body.get("links") or {}).get("next")
        return rows, pages
