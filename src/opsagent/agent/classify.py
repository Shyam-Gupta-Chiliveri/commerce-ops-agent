from __future__ import annotations

import re

RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("double_charge", ("zweimal abgebucht", "doppelt abgebucht", "double charge")),
    ("cancel_marketing", ("keine mails", "newsletter", "abmelden", "unsubscribe")),
    ("product_complaint", ("ausgelaufen", "kaputt", "defekt")),
    ("exchange_size", ("größe", "zu klein", "zu groß")),
    ("refund", ("erstatt", "geld zurück", "refund")),
    ("where_is_order", ("nicht da", "wo bleibt", "sendung", "tracking", "rennen")),
)


def classify(text: str) -> tuple[str, str | None]:
    lowered = text.lower()
    intent = "other"
    for name, needles in RULES:
        if any(needle in lowered for needle in needles):
            intent = name
            break
    match = re.search(r"größe\s+(\d+)", lowered)
    size = match.group(1) if match else None
    return intent, size
