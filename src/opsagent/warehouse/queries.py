from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Ticket:
    ticket_id: int
    subject: str
    description: str
    brand: str
    order_name: str | None
    email: str
    first_name: str


@dataclass
class Line:
    sku: str
    title: str
    variant_title: str
    price: str


@dataclass
class Order:
    order_id: int
    order_name: str
    financial_status: str
    fulfillment_status: str | None
    currency: str
    total_price: str
    promised_ship_date: str | None
    delivered_at: str | None
    tracking_number: str | None
    lines: list[Line]
    email: str = ""


@dataclass
class Event:
    metric_name: str
    happened_at: str
    subject: str
    campaign: str
    order_name: str


@dataclass
class Supply:
    order_number: str
    supplier_name: str
    sku: str
    quantity: float
    quantity_received: float
    decision: str | None
    issue_codes: str | None


@dataclass
class Stock:
    sku: str
    option_label: str
    available: int


@dataclass
class Txn:
    kind: str
    status: str
    amount: str
    created_at: str


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_ticket(conn, ticket_id: int) -> Ticket:
    row = conn.execute("SELECT * FROM zendesk_tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise KeyError(ticket_id)
    return Ticket(
        ticket_id=row["ticket_id"],
        subject=row["subject"],
        description=row["description"],
        brand=row["brand"],
        order_name=row["order_name"],
        email=row["requester_email"],
        first_name=row["first_name"],
    )


def get_order(conn, order_name: str | None) -> Order | None:
    if not order_name:
        return None
    row = conn.execute("SELECT * FROM shopify_orders WHERE order_name = ?", (order_name,)).fetchone()
    if row is None:
        return None
    lines = [
        Line(sku=item["sku"], title=item["title"], variant_title=item["variant_title"], price=item["price"])
        for item in conn.execute("SELECT * FROM shopify_line_items WHERE order_id = ? ORDER BY line_id", (row["order_id"],))
    ]
    return Order(
        order_id=row["order_id"],
        order_name=row["order_name"],
        financial_status=row["financial_status"],
        fulfillment_status=row["fulfillment_status"],
        currency=row["currency"],
        total_price=row["total_price"],
        promised_ship_date=row["promised_ship_date"],
        delivered_at=row["delivered_at"],
        tracking_number=row["tracking_number"],
        lines=lines,
        email=row["email"] or "",
    )


def events_for(conn, email: str) -> list[Event]:
    return [
        Event(
            metric_name=row["metric_name"],
            happened_at=row["happened_at"],
            subject=row["subject"],
            campaign=row["campaign"],
            order_name=row["order_name"],
        )
        for row in conn.execute(
            "SELECT * FROM klaviyo_events WHERE email = ? ORDER BY happened_at",
            (email,),
        )
    ]


def supply_for(conn, sku: str) -> list[Supply]:
    return [
        Supply(
            order_number=row["order_number"],
            supplier_name=row["supplier_name"],
            sku=row["sku"],
            quantity=row["quantity"],
            quantity_received=row["quantity_received"],
            decision=row["decision"],
            issue_codes=row["issue_codes"],
        )
        for row in conn.execute(
            """
            SELECT po.order_number, po.supplier_name, pol.sku, pol.quantity, pol.quantity_received,
                   br.decision, br.issue_codes
            FROM anvyl_po_lines pol
            JOIN anvyl_purchase_orders po ON po.po_id = pol.po_id
            LEFT JOIN bill_reviews br ON br.po_number = po.order_number
            WHERE pol.sku = ?
            """,
            (sku,),
        )
    ]


def available(conn, sku: str) -> int:
    row = conn.execute("SELECT available FROM inventory WHERE sku = ?", (sku,)).fetchone()
    return int(row["available"]) if row else 0


def alternatives(conn, sku: str) -> list[Stock]:
    return [
        Stock(sku=row["sku"], option_label=row["option_label"], available=row["available"])
        for row in conn.execute(
            """
            SELECT i2.sku, i2.option_label, i2.available
            FROM inventory i1
            JOIN inventory i2 ON i2.product_id = i1.product_id
            WHERE i1.sku = ? AND i2.sku != i1.sku AND i2.available > 0
            ORDER BY i2.sku
            """,
            (sku,),
        )
    ]


def stock_for_size(conn, sku: str, size: str) -> Stock | None:
    row = conn.execute(
        """
        SELECT i2.sku, i2.option_label, i2.available
        FROM inventory i1
        JOIN inventory i2 ON i2.product_id = i1.product_id
        WHERE i1.sku = ? AND (i2.option_label = ? OR i2.option_label LIKE ?)
        ORDER BY i2.available DESC
        LIMIT 1
        """,
        (sku, size, size + " / %"),
    ).fetchone()
    if row is None:
        return None
    return Stock(sku=row["sku"], option_label=row["option_label"], available=row["available"])


def transactions(conn, order_id: int) -> list[Txn]:
    return [
        Txn(kind=row["kind"], status=row["status"], amount=row["amount"], created_at=row["created_at"])
        for row in conn.execute(
            "SELECT * FROM shopify_transactions WHERE order_id = ? AND status = 'success' ORDER BY created_at",
            (order_id,),
        )
    ]
