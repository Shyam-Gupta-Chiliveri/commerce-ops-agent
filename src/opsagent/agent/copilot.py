from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from opsagent.agent.classify import classify
from opsagent.agent.draft import CaseFile, critique, grounded, ungrounded
from opsagent.agent.fraud import scan as scan_fraud
from opsagent.settings import Settings
from opsagent.warehouse import queries


@dataclass
class Review:
    ticket_id: int
    intent: str
    actions: list[str]
    reply_de: str
    reply_en: str
    internal_note: str
    critic: list[str]
    executed_writes: list[str]
    latency_ms: float
    cost_eur: float
    drafter: str
    fraud: list[dict]


def review_ticket(db_path: Path, ticket_id: int, settings: Settings, drafter: str = "grounded") -> Review:
    started = time.perf_counter()
    conn = queries.connect(db_path)
    try:
        ticket = queries.get_ticket(conn, ticket_id)
        intent, size = classify(f"{ticket.subject}\n{ticket.description}")
        order = queries.get_order(conn, ticket.order_name)
        supply = []
        alternatives = []
        requested = None
        on_hand = 0
        txns = []
        if order:
            for line in order.lines:
                supply.extend(queries.supply_for(conn, line.sku))
                alternatives.extend(queries.alternatives(conn, line.sku))
                on_hand = queries.available(conn, line.sku)
                if size:
                    requested = queries.stock_for_size(conn, line.sku, size)
            if intent in {"refund", "double_charge"}:
                txns = queries.transactions(conn, order.order_id)
        events = queries.events_for(conn, ticket.email)
        if order and order.email and order.email.lower() != (ticket.email or "").lower():
            seen = {(event.metric_name, event.happened_at, event.subject) for event in events}
            for event in queries.events_for(conn, order.email):
                key = (event.metric_name, event.happened_at, event.subject)
                if key not in seen:
                    events.append(event)
        fraud = scan_fraud(ticket, order, events)
    finally:
        conn.close()

    case = CaseFile(
        ticket=ticket,
        intent=intent,
        requested_size=size,
        order=order,
        events=events,
        supply=supply,
        on_hand=on_hand,
        alternatives=alternatives,
        requested_stock=requested,
        transactions=txns,
        settings=settings,
        fraud=fraud,
    )
    render = grounded if drafter == "grounded" else ungrounded
    reply_de, reply_en, actions = render(case)
    findings = critique(case, reply_de)
    note = _note(case, actions)
    return Review(
        ticket_id=ticket_id,
        intent=intent,
        actions=actions,
        reply_de=reply_de,
        reply_en=reply_en,
        internal_note=note,
        critic=findings,
        executed_writes=[],
        latency_ms=(time.perf_counter() - started) * 1000,
        cost_eur=0.0,
        drafter=drafter,
        fraud=fraud,
    )


def _note(case: CaseFile, actions: list[str]) -> str:
    order = case.order.order_name if case.order else "keine"
    status = case.order.financial_status if case.order else "-"
    fulfillment = "unfulfilled" if case.order and not case.order.fulfillment_status else (case.order.fulfillment_status if case.order else "-")
    blocks = ", ".join(f"{row.order_number} {row.decision} {row.issue_codes}" for row in case.blocked) or "kein Supply-Block"
    return (
        "INTERN — nicht an die Kundin senden.\n"
        f"Ticket {case.ticket.ticket_id}, Intent {case.intent}, Marke {case.ticket.brand}.\n"
        f"Shopify {order}, financial_status {status}, fulfillment_status {fulfillment}, Bestand {case.on_hand}.\n"
        f"Supply: {blocks}.\n"
        f"Aktionen vorgeschlagen, nicht ausgeführt: {', '.join(actions)}.\n"
        "Schreibzugriff auf Shopify, Resolvia, Klaviyo und Sage ist in diesem Lauf nicht verdrahtet."
    )
