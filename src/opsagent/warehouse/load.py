from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import httpx

from opsagent.connectors import build_clients
from opsagent.fixture_io import quellberg_csv
from opsagent.paths import SCHEMA_PATH
from opsagent.rules import review_bill
from opsagent.settings import Settings

BRAND_FIELD = 1001
ORDER_FIELD = 1002


@dataclass
class SyncStats:
    shopify_orders: int
    shopify_pages: int
    zendesk_tickets: int
    zendesk_pages: int
    klaviyo_events: int
    klaviyo_pages: int
    anvyl_orders: int
    anvyl_pages: int
    sage_bills: int
    sage_pages: int
    ap_reviews: int


def sync(
    http: httpx.Client,
    settings: Settings,
    db_path: Path,
    bronze_dir: Path | None = None,
    live_http: httpx.Client | None = None,
) -> SyncStats:
    shopify, zendesk, klaviyo, anvyl, sage = build_clients(http, settings, live_http)
    orders, order_pages = _live_or_empty(shopify.list_orders)
    variants, _variant_pages = _live_or_empty(shopify.list_variants)
    tickets, ticket_pages = zendesk.list_tickets()
    users = zendesk.list_users()
    events, event_pages = klaviyo.list_events()
    purchase_orders, po_pages = anvyl.list_purchase_orders()
    bills, bill_pages = sage.list_purchase_invoices()
    comments = {ticket["id"]: zendesk.list_comments(ticket["id"]) for ticket in tickets}
    transactions = {order["id"]: shopify.list_transactions(order["id"]) for order in orders}

    if bronze_dir is not None:
        bronze_dir.mkdir(parents=True, exist_ok=True)
        _dump(bronze_dir / "shopify_orders.json", orders)
        _dump(bronze_dir / "zendesk_tickets.json", tickets)
        _dump(bronze_dir / "klaviyo_events.json", events)
        _dump(bronze_dir / "anvyl_purchase_orders.json", purchase_orders)
        _dump(bronze_dir / "sage_purchase_invoices.json", bills)

    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _load_shopify(conn, orders, variants, transactions)
        _load_zendesk(conn, tickets, users, comments)
        _load_klaviyo(conn, events)
        _load_supply(conn, purchase_orders, bills)
        ap_count = _load_quellberg(conn, quellberg_csv())
        conn.commit()
    finally:
        conn.close()

    return SyncStats(
        shopify_orders=len(orders),
        shopify_pages=order_pages,
        zendesk_tickets=len(tickets),
        zendesk_pages=ticket_pages,
        klaviyo_events=len(events),
        klaviyo_pages=event_pages,
        anvyl_orders=len(purchase_orders),
        anvyl_pages=po_pages,
        sage_bills=len(bills),
        sage_pages=bill_pages,
        ap_reviews=ap_count,
    )


def account_counts(http: httpx.Client, settings: Settings, live_http: httpx.Client | None = None) -> dict[str, int]:
    """Count records on each connected account. The example inbox is loaded separately."""
    from opsagent.settings import klaviyo_base, sage_base, shopify_base, zendesk_base

    shopify, zendesk, klaviyo, _anvyl, sage = build_clients(http, settings, live_http)
    found: dict[str, int] = {}

    def count(name: str, base: str, call) -> None:
        if not base.startswith("https://"):
            return
        try:
            rows, _pages = call()
        except httpx.HTTPError:
            return
        found[name] = len(rows)

    count("shopify_orders", shopify_base(settings), shopify.list_orders)
    count("zendesk_tickets", zendesk_base(settings), zendesk.list_tickets)
    count("klaviyo_events", klaviyo_base(settings), klaviyo.list_events)
    count("sage_bills", sage_base(settings), sage.list_purchase_invoices)
    return found


def _live_or_empty(call):
    """A 403 from a live account leaves that list empty so the other sources still load."""
    try:
        return call()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        print(exc.response.text[:400])
        return [], 0


def _dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _brand(tags: str) -> str:
    for part in (tags or "").split(","):
        part = part.strip()
        if part.startswith("brand:"):
            return part.split(":", 1)[1].strip()
    return ""


def _note(order: dict, name: str) -> str | None:
    for item in order.get("note_attributes") or []:
        if item.get("name") == name:
            return item.get("value")
    return None


def _custom(ticket: dict, field_id: int) -> str | None:
    for field in ticket.get("custom_fields") or []:
        if field.get("id") == field_id:
            return field.get("value")
    return None


def _load_shopify(conn, orders, variants, transactions) -> None:
    for order in orders:
        fulfillment = (order.get("fulfillments") or [None])[0]
        conn.execute(
            """
            INSERT INTO shopify_orders (
              order_id, order_name, email, first_name, brand, created_at,
              financial_status, fulfillment_status, currency, total_price,
              promised_ship_date, delivered_at, tracking_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["id"],
                order["name"],
                order.get("email") or "",
                (order.get("customer") or {}).get("first_name"),
                _brand(order.get("tags") or ""),
                order["created_at"],
                order["financial_status"],
                order.get("fulfillment_status"),
                order["currency"],
                order["total_price"],
                _note(order, "promised_ship_date"),
                None if order.get("fulfillment_status") != "fulfilled" or not fulfillment else fulfillment.get("created_at"),
                None if not fulfillment else fulfillment.get("tracking_number"),
            ),
        )
        for line in order["line_items"]:
            conn.execute(
                """
                INSERT INTO shopify_line_items (line_id, order_id, sku, title, variant_title, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (line["id"], order["id"], line["sku"], line["title"], line["variant_title"], line["quantity"], line["price"]),
            )
        for txn in transactions.get(order["id"], []):
            conn.execute(
                """
                INSERT INTO shopify_transactions (transaction_id, order_id, kind, status, amount, gateway, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (txn["id"], order["id"], txn["kind"], txn["status"], txn["amount"], txn["gateway"], txn["created_at"]),
            )
    seen_skus: set[str] = set()
    for variant in variants:
        sku = variant.get("sku") or ""
        if not sku or sku in seen_skus:
            continue
        seen_skus.add(sku)
        conn.execute(
            "INSERT INTO inventory (sku, product_id, option_label, title, available) VALUES (?, ?, ?, ?, ?)",
            (
                sku,
                variant.get("product_id"),
                variant.get("option") or variant.get("option1") or "",
                variant.get("title") or "",
                variant["available"] if variant.get("available") is not None else variant.get("inventory_quantity") or 0,
            ),
        )


def _load_zendesk(conn, tickets, users, comments) -> None:
    by_id = {user["id"]: user for user in users}
    for user in users:
        conn.execute(
            "INSERT INTO zendesk_users (user_id, name, email, locale) VALUES (?, ?, ?, ?)",
            (user["id"], user["name"], user["email"], user["locale"]),
        )
    for ticket in tickets:
        user = by_id.get(ticket["requester_id"]) or {"email": "", "name": "Customer"}
        conn.execute(
            """
            INSERT INTO zendesk_tickets (
              ticket_id, subject, status, brand, order_name, requester_id,
              requester_email, first_name, created_at, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket["id"],
                ticket["subject"],
                ticket["status"],
                _custom(ticket, BRAND_FIELD),
                _custom(ticket, ORDER_FIELD),
                ticket["requester_id"],
                user["email"],
                user["name"].split()[0],
                ticket["created_at"],
                ticket.get("description") or "",
            ),
        )
        for comment in comments.get(ticket["id"], []):
            conn.execute(
                """
                INSERT INTO zendesk_comments (comment_id, ticket_id, author_id, is_public, body, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (comment["id"], ticket["id"], comment["author_id"], 1 if comment["public"] else 0, comment["body"], comment["created_at"]),
            )


def _load_klaviyo(conn, events) -> None:
    for event in events:
        props = event["properties"]
        conn.execute(
            """
            INSERT INTO klaviyo_events (event_id, email, metric_name, happened_at, subject, campaign, order_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["email"],
                event["metric"],
                event["datetime"],
                props.get("Subject") or "",
                props.get("Campaign Name") or "",
                props.get("Order") or "",
            ),
        )


def _load_supply(conn, purchase_orders, bills) -> None:
    po_by_number = {}
    for po in purchase_orders:
        conn.execute(
            """
            INSERT INTO anvyl_purchase_orders (po_id, order_number, supplier_name, status, ships_on)
            VALUES (?, ?, ?, ?, ?)
            """,
            (po["id"], po["order_number"], po["supplier"]["name"], po["status"], po["ships_on"]),
        )
        for item in po["order_items"]:
            conn.execute(
                """
                INSERT INTO anvyl_po_lines (po_id, sku, quantity, quantity_received, unit_price_micros)
                VALUES (?, ?, ?, ?, ?)
                """,
                (po["id"], item["sku"], item["quantity"], item["quantity_received"], item["unit_price_micros"]),
            )
        po_by_number[po["order_number"]] = po

    for bill in bills:
        po_number = bill["vendor_reference"]
        conn.execute(
            """
            INSERT INTO sage_bills (bill_id, po_number, vendor_name, sage_status, bill_date, reference, total_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bill["id"],
                po_number,
                bill["contact"]["displayed_as"],
                bill["status"]["id"],
                bill["date"],
                bill["reference"],
                bill["total_amount"],
            ),
        )
        po = po_by_number[po_number]
        po_lines = {item["sku"]: item for item in po["order_items"]}
        for line in bill["invoice_lines"]:
            conn.execute(
                """
                INSERT INTO sage_bill_lines (bill_id, sku, quantity, unit_price, net_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (bill["id"], line["sku"], line["quantity"], line["unit_price"], line["net_amount"]),
            )
            ordered = po_lines[line["sku"]]
            ordered_net = ordered["quantity"] * ordered["unit_price_micros"] / 1_000_000
            billed_net = float(line["net_amount"])
            decision, issues = review_bill(
                ordered_qty=float(ordered["quantity"]),
                billed_qty=float(line["quantity"]),
                ordered_net=ordered_net,
                billed_net=billed_net,
            )
            conn.execute(
                """
                INSERT INTO bill_reviews (
                  bill_id, po_number, decision, issue_codes, ordered_qty, billed_qty, ordered_net, billed_net
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bill["id"],
                    po_number,
                    decision,
                    ",".join(issues),
                    float(ordered["quantity"]),
                    float(line["quantity"]),
                    ordered_net,
                    billed_net,
                ),
            )


def _load_quellberg(conn, path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for raw in reader:
            row = {key.strip(): (value or "").strip() for key, value in raw.items()}
            gross = row["gross_eur"]
            conn.execute(
                """
                INSERT INTO ap_invoice_reviews (
                  source_file, decision, priority, vendor, invoice_number, invoice_date,
                  po, gross_eur, issue_codes, summary, origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["file"],
                    row["decision"],
                    row["priority"],
                    row["vendor"],
                    row["invoice_number"],
                    row["date"],
                    row["po"] or None,
                    float(gross) if gross else None,
                    row["issues"],
                    row["summary"],
                    "invoice-review-agent",
                ),
            )
            count += 1
    return count
