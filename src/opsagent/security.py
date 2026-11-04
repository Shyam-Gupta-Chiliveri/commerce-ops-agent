from __future__ import annotations

import base64
import hashlib
import hmac


def shopify_hmac(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def shopify_hmac_valid(secret: str, body: bytes, given: str) -> bool:
    expected = shopify_hmac(secret, body)
    return hmac.compare_digest(expected, given or "")
