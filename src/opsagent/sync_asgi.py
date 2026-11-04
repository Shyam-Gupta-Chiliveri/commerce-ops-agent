"""Sync httpx transport for the in-process fixture app.

httpx.ASGITransport is async-only. The connectors stay synchronous, which is
what a script and a test should be, so this transport runs the ASGI app on a
short event loop per request.
"""

from __future__ import annotations

import asyncio

import httpx


class SyncASGITransport(httpx.BaseTransport):
    def __init__(self, app):
        self.app = app

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(key.lower(), value) for key, value in request.headers.raw],
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query,
            "server": (request.url.host, request.url.port or 80),
            "client": ("127.0.0.1", 123),
            "root_path": "",
        }
        status_code = 500
        raw_headers: list[tuple[bytes, bytes]] = []
        chunks: list[bytes] = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            nonlocal status_code, raw_headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                raw_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    chunks.append(chunk)

        asyncio.run(self.app(scope, receive, send))
        return httpx.Response(status_code, headers=raw_headers, content=b"".join(chunks))
