"""Local page for the one agent that reads Shopify, Zendesk, Klaviyo, Anvyl and Sage."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from opsagent.agent.classify import classify
from opsagent.agent.copilot import review_ticket
from opsagent.eval.run import evaluate
from opsagent.mockapi.app import create_app
from opsagent.paths import VAR_DIR
from opsagent.settings import Settings, load_settings
from opsagent.sync_asgi import SyncASGITransport
from opsagent.warehouse.load import sync
from opsagent.warehouse.queries import connect

PAGE = Path(__file__).with_name("prototype.html").read_text(encoding="utf-8")

ISSUE_TEXT = {
    "QTY_OVER": ("The bill counts more pieces than were ordered.", "Die Rechnung zählt mehr Stück, als bestellt wurden."),
    "OVER_PO_VALUE": ("The bill amount is higher than the purchase order.", "Der Rechnungsbetrag liegt über der Bestellung."),
    "IBAN_SHARED": ("The same bank account appears on more than one supplier.", "Dieselbe Bankverbindung steht bei mehr als einem Lieferanten."),
    "IBAN_INVALID": ("The bank account number is not valid.", "Die Bankverbindung ist ungültig."),
    "ITEMS_NOT_ORDERED": ("The bill includes items that are not on the purchase order.", "Die Rechnung enthält Positionen, die nicht bestellt wurden."),
    "NO_PO": ("The invoice has no purchase order.", "Auf der Rechnung fehlt die Bestellung."),
    "PO_NO_VALUE": ("The purchase order has no amount.", "Die Bestellung hat keinen Betrag."),
    "MISSING_FIELDS": ("Required fields are missing.", "Pflichtfelder fehlen."),
    "NOT_AN_INVOICE": ("This file is not an invoice.", "Diese Datei ist keine Rechnung."),
    "MATH_ERROR": ("The amounts on the invoice do not add up.", "Die Beträge auf der Rechnung gehen nicht auf."),
    "VAT_ERROR": ("The tax amount does not match.", "Die Steuer stimmt nicht."),
    "DUPLICATE": ("This invoice appears twice.", "Diese Rechnung kommt doppelt vor."),
    "HAS_DUPLICATE": ("A duplicate of this invoice is still in the queue.", "Ein Duplikat dieser Rechnung liegt noch in der Warteschlange."),
}


def _prepare(settings: Settings):
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    fixture = create_app(settings)
    http = httpx.Client(transport=SyncASGITransport(fixture), base_url="http://mock")
    db = VAR_DIR / "warehouse.sqlite"
    stats = sync(http, settings, db, VAR_DIR / "bronze")
    return db, stats


def create_prototype(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db, stats = _prepare(settings)
    grounded = evaluate(db, settings, "grounded")
    app = FastAPI(title="Commerce ops agent")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return PAGE

    @app.get("/api/summary")
    def summary():
        return {
            "shopify_orders": stats.shopify_orders,
            "zendesk_tickets": stats.zendesk_tickets,
            "klaviyo_events": stats.klaviyo_events,
            "anvyl_orders": stats.anvyl_orders,
            "sage_bills": stats.sage_bills,
            "ap_reviews": stats.ap_reviews,
            "grounded_passed": grounded.passed,
            "grounded_total": grounded.total,
        }

    def _reasons(codes: str | None) -> tuple[list[str], list[str]]:
        english, german = [], []
        for code in (codes or "").split(","):
            code = code.strip()
            if not code:
                continue
            pair = ISSUE_TEXT.get(code)
            english.append(pair[0] if pair else code)
            german.append(pair[1] if pair else code)
        return english, german

    @app.get("/api/supply")
    def supply():
        conn = connect(db)
        try:
            rows = conn.execute(
                """
                SELECT br.bill_id, br.po_number, br.decision, br.issue_codes,
                       br.ordered_qty, br.billed_qty, br.ordered_net, br.billed_net,
                       sb.vendor_name, sb.sage_status
                FROM bill_reviews br
                LEFT JOIN sage_bills sb ON sb.bill_id = br.bill_id
                ORDER BY CASE WHEN br.decision = 'INVESTIGATE' THEN 0 ELSE 1 END, br.bill_id
                """
            ).fetchall()
        finally:
            conn.close()
        payload = []
        for row in rows:
            english, german = _reasons(row["issue_codes"])
            payload.append(
                {
                    "bill_id": row["bill_id"],
                    "po_number": row["po_number"],
                    "supplier": row["vendor_name"] or "",
                    "decision": row["decision"],
                    "accounts_status": row["sage_status"] or "",
                    "ordered_qty": row["ordered_qty"],
                    "billed_qty": row["billed_qty"],
                    "ordered_net": row["ordered_net"],
                    "billed_net": row["billed_net"],
                    "reasons_en": english,
                    "reasons_de": german,
                }
            )
        return payload

    @app.get("/api/report")
    def report():
        conn = connect(db)
        try:
            ap = conn.execute(
                """
                SELECT COUNT(*) AS documents,
                       SUM(decision = 'INVESTIGATE') AS investigate,
                       SUM(decision = 'APPROVE') AS approve,
                       ROUND(SUM(gross_eur), 2) AS gross,
                       SUM(gross_eur IS NULL) AS missing_gross
                FROM ap_invoice_reviews
                """
            ).fetchone()
            counts: dict[str, int] = {}
            for row in conn.execute("SELECT issue_codes FROM ap_invoice_reviews"):
                for code in (row["issue_codes"] or "").split(","):
                    code = code.strip()
                    if code:
                        counts[code] = counts.get(code, 0) + 1
            blocked = conn.execute(
                """
                SELECT ticket_id, first_name, order_name, blocked_po, supplier_name
                FROM gold_customer_service
                WHERE blocked_po IS NOT NULL
                ORDER BY ticket_id
                """
            ).fetchall()
            open_tickets = conn.execute("SELECT COUNT(*) FROM zendesk_tickets WHERE status = 'open'").fetchone()[0]
        finally:
            conn.close()
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        issues = []
        for code, count in top:
            pair = ISSUE_TEXT.get(code)
            issues.append(
                {
                    "code": code,
                    "count": count,
                    "text_en": pair[0] if pair else code,
                    "text_de": pair[1] if pair else code,
                }
            )
        return {
            "sync": {
                "shopify_orders": stats.shopify_orders,
                "shopify_pages": stats.shopify_pages,
                "zendesk_tickets": stats.zendesk_tickets,
                "zendesk_pages": stats.zendesk_pages,
                "klaviyo_events": stats.klaviyo_events,
                "klaviyo_pages": stats.klaviyo_pages,
                "anvyl_orders": stats.anvyl_orders,
                "sage_bills": stats.sage_bills,
                "ap_reviews": stats.ap_reviews,
            },
            "service": {
                "open_tickets": open_tickets,
                "grounded_passed": grounded.passed,
                "grounded_total": grounded.total,
                "cost_eur": grounded.cost_eur,
                "blocked": [dict(row) for row in blocked],
            },
            "invoices": {
                "documents": ap["documents"],
                "investigate": ap["investigate"],
                "approve": ap["approve"],
                "gross": ap["gross"],
                "missing_gross": ap["missing_gross"],
                "issues": issues,
            },
        }

    @app.get("/api/tickets")
    def tickets():
        conn = connect(db)
        try:
            rows = conn.execute(
                """
                SELECT ticket_id, subject, description, brand, order_name, first_name
                FROM zendesk_tickets
                ORDER BY ticket_id
                """
            ).fetchall()
        finally:
            conn.close()
        payload = []
        for row in rows:
            intent, _size = classify(f"{row['subject']}\n{row['description']}")
            payload.append(
                {
                    "ticket_id": row["ticket_id"],
                    "subject": row["subject"],
                    "brand": row["brand"],
                    "order_name": row["order_name"],
                    "first_name": row["first_name"],
                    "intent": intent,
                }
            )
        return payload

    @app.get("/api/tickets/{ticket_id}")
    def ticket(ticket_id: int):
        try:
            result = review_ticket(db, ticket_id, settings)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown ticket") from exc
        conn = connect(db)
        try:
            row = conn.execute(
                """
                SELECT t.subject, t.description, t.brand, t.order_name, t.first_name, t.requester_email,
                       o.financial_status, o.fulfillment_status, o.total_price, o.currency,
                       li.sku, li.title, li.variant_title, inv.available
                FROM zendesk_tickets t
                LEFT JOIN shopify_orders o ON o.order_name = t.order_name
                LEFT JOIN shopify_line_items li ON li.order_id = o.order_id
                LEFT JOIN inventory inv ON inv.sku = li.sku
                WHERE t.ticket_id = ?
                ORDER BY li.line_id
                LIMIT 1
                """,
                (ticket_id,),
            ).fetchone()
            events = []
            supply = None
            if row is not None:
                events = conn.execute(
                    """
                    SELECT metric_name, happened_at, subject, campaign
                    FROM klaviyo_events
                    WHERE email = ?
                    ORDER BY happened_at
                    """,
                    (row["requester_email"],),
                ).fetchall()
                if row["sku"]:
                    supply = conn.execute(
                        """
                        SELECT po.order_number, po.supplier_name, br.decision, br.issue_codes
                        FROM anvyl_po_lines pol
                        JOIN anvyl_purchase_orders po ON po.po_id = pol.po_id
                        LEFT JOIN bill_reviews br ON br.po_number = po.order_number
                        WHERE pol.sku = ?
                        ORDER BY CASE WHEN br.decision = 'INVESTIGATE' THEN 0 ELSE 1 END
                        LIMIT 1
                        """,
                        (row["sku"],),
                    ).fetchone()
        finally:
            conn.close()
        shopify = None
        if row is not None and row["financial_status"]:
            shopify = {
                "order_name": row["order_name"],
                "financial_status": row["financial_status"],
                "fulfillment_status": row["fulfillment_status"] or "unfulfilled",
                "title": " ".join(part for part in (row["title"], row["variant_title"]) if part),
                "available": row["available"] if row["available"] is not None else 0,
                "sku": row["sku"],
                "total_price": row["total_price"],
                "currency": row["currency"],
            }
        return {
            "ticket_id": result.ticket_id,
            "brand": row["brand"] if row else "",
            "first_name": row["first_name"] if row else "",
            "order_name": row["order_name"] if row else "",
            "subject": row["subject"] if row else "",
            "customer_message": row["description"] if row else "",
            "intent": result.intent,
            "actions": result.actions,
            "reply_de": result.reply_de,
            "reply_en": result.reply_en,
            "internal_note": result.internal_note,
            "critic": result.critic,
            "executed_writes": result.executed_writes,
            "fraud": result.fraud,
            "shopify": shopify,
            "klaviyo": [
                {
                    "metric": event["metric_name"],
                    "happened_at": event["happened_at"],
                    "subject": event["subject"],
                    "campaign": event["campaign"],
                }
                for event in events
            ],
            "supply": None
            if supply is None
            else {
                "order_number": supply["order_number"],
                "supplier_name": supply["supplier_name"],
                "decision": supply["decision"],
                "issue_codes": supply["issue_codes"],
            },
        }

    return app
