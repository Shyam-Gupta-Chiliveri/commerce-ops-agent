from __future__ import annotations

import sqlite3
from collections import Counter

from opsagent.eval.run import EvalReport
from opsagent.warehouse.load import SyncStats


def render_report(db_path, stats: SyncStats, evals: list[EvalReport]) -> str:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ap = conn.execute(
            """
            SELECT
              COUNT(*) AS documents,
              SUM(decision = 'INVESTIGATE') AS investigate,
              SUM(decision = 'APPROVE') AS approve,
              ROUND(SUM(gross_eur), 2) AS gross,
              SUM(gross_eur IS NULL) AS missing_gross
            FROM ap_invoice_reviews
            """
        ).fetchone()
        codes: Counter[str] = Counter()
        for row in conn.execute("SELECT issue_codes FROM ap_invoice_reviews"):
            for code in (row["issue_codes"] or "").split(","):
                if code:
                    codes[code] += 1
        blocked = conn.execute(
            """
            SELECT ticket_id, order_name, total_price, currency, blocked_po, supplier_name, issue_codes, sku
            FROM gold_customer_service
            WHERE blocked_po IS NOT NULL
            """
        ).fetchall()
        bills = conn.execute(
            "SELECT decision, COUNT(*) AS n FROM bill_reviews GROUP BY decision ORDER BY decision"
        ).fetchall()
        open_tickets = conn.execute("SELECT COUNT(*) FROM zendesk_tickets WHERE status = 'open'").fetchone()[0]
    finally:
        conn.close()

    bill_line = ", ".join(f"{row['decision']} {row['n']}" for row in bills)
    blocked_line = (
        "\n".join(
            f"- Ticket {row['ticket_id']} {row['order_name']} SKU {row['sku']} "
            f"{row['total_price']} {row['currency']} blockiert durch {row['blocked_po']} "
            f"({row['supplier_name']}, {row['issue_codes']})"
            for row in blocked
        )
        or "- keine"
    )
    code_line = ", ".join(f"{name} {count}" for name, count in codes.most_common())
    eval_line = "\n".join(f"- {report.drafter}: {report.passed}/{report.total}, violations {report.violations}, EUR {report.cost_eur:.4f}" for report in evals)
    return f"""# Customer-service and supply report

Clock is frozen at the fixture date so this report does not change tomorrow.
Harbor House orders, tickets and campaigns are fixtures. The supplier-invoice queue at the bottom is the real output of invoice-review-agent.

## Sync

- Shopify orders: {stats.shopify_orders} in {stats.shopify_pages} pages
- Zendesk tickets: {stats.zendesk_tickets} in {stats.zendesk_pages} pages
- Klaviyo events: {stats.klaviyo_events} in {stats.klaviyo_pages} pages
- Anvyl purchase orders: {stats.anvyl_orders} in {stats.anvyl_pages} pages
- Sage purchase invoices: {stats.sage_bills} in {stats.sage_pages} pages
- Invoice-review documents: {stats.ap_reviews}

## Customer service

Open tickets: {open_tickets}

Apparel bills checked against Anvyl: {bill_line}

Orders a customer is waiting on because the supplier bill failed the quantity check:

{blocked_line}

## Supplier invoices from invoice-review-agent

Documents {ap['documents']}, investigate {ap['investigate']}, approve {ap['approve']}.
Gross on the documents that have one: EUR {float(ap['gross']):,.2f}. Documents without a gross amount: {ap['missing_gross']}.
The duplicate Kolb invoice is still in this sum until a person removes it.

Issue codes: {code_line}

## Drafter measurement

{eval_line}

The grounded drafter may only say what the warehouse rows support. The ungrounded drafter answers from the ticket text and is here to show the failure mode, not a live model. Model cost is 0 in both rows because no model API is called. A Claude or OpenAI drafter would sit behind the same function and would still have to pass the critic before a person sends anything.
"""
