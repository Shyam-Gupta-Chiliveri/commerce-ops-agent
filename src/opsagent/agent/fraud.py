"""Rule check for payment scams across the ticket, the shop, and email."""

from __future__ import annotations

from opsagent.warehouse.queries import Event, Order, Ticket

NEEDLES: tuple[str, ...] = (
    "paysafecard",
    "gift card",
    "gutscheincode",
    "zollgebühr",
    "zollgebuehr",
    "customs fee",
    "bitcoin",
    "krypto",
    "western union",
    "whatsapp",
    "wire transfer",
)


def _hit(text: str) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in NEEDLES)


def scan(ticket: Ticket, order: Order | None, events: list[Event]) -> list[dict]:
    found: list[dict] = []
    message = f"{ticket.subject}\n{ticket.description}"
    if _hit(message):
        found.append(
            {
                "source": "Zendesk",
                "text_de": "Die Nachricht verlangt eine Zahlung außerhalb des Shops, zum Beispiel per Paysafecard oder als Gebühr. So nimmt Harbor kein Geld an.",
                "text_en": "The message asks for a payment outside the shop, such as a Paysafecard or a fee. Harbor does not take money that way.",
            }
        )
    if order is not None and ticket.email and order.email and ticket.email.lower() != order.email.lower():
        found.append(
            {
                "source": "Shopify",
                "text_de": f"Das Ticket kommt von {ticket.email}. Bestellung {order.order_name} gehört zu {order.email}.",
                "text_en": f"The ticket was opened by {ticket.email}. Order {order.order_name} belongs to {order.email}.",
            }
        )
    elif order is not None and _hit(message) and order.financial_status == "paid":
        shipped = " und versendet" if order.fulfillment_status == "fulfilled" else ""
        shipped_en = " and shipped" if order.fulfillment_status == "fulfilled" else ""
        found.append(
            {
                "source": "Shopify",
                "text_de": f"Bestellung {order.order_name} ist bereits bezahlt{shipped}. Im Shop steht keine offene Gebühr.",
                "text_en": f"Order {order.order_name} is already paid{shipped_en}. The shop shows no fee left to pay.",
            }
        )
    for event in events:
        blob = f"{event.subject} {event.campaign}"
        if not _hit(blob):
            continue
        title = event.subject or event.campaign
        found.append(
            {
                "source": "Klaviyo",
                "text_de": f"Im E-Mail-Verlauf liegt „{title}“. Das ist keine Harbor-Kampagne.",
                "text_en": f"The email history contains “{title}”. That is not a Harbor campaign.",
            }
        )
        break
    return found
