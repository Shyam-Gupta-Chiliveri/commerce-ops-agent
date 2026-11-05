from __future__ import annotations

from opsagent.agent.copilot import review_ticket
from opsagent.eval.run import evaluate
from opsagent.warehouse.queries import connect


def test_pagination_reaches_every_system(synced):
    _http, _settings, _db, stats = synced
    assert stats.shopify_orders == 12
    assert stats.shopify_pages == 6
    assert stats.zendesk_tickets == 12
    assert stats.zendesk_pages == 6
    assert stats.klaviyo_events == 9
    assert stats.klaviyo_pages == 5
    assert stats.anvyl_orders == 3
    assert stats.anvyl_pages == 2
    assert stats.sage_bills == 3
    assert stats.sage_pages == 2
    assert stats.ap_reviews == 16


def test_hero_ticket_is_blocked_by_the_supplier_bill(synced):
    _http, _settings, db, _stats = synced
    conn = connect(db)
    row = conn.execute(
        """
        SELECT order_name, sku, blocked_po, supplier_name, issue_codes, total_price
        FROM gold_customer_service
        WHERE ticket_id = 44021
        """
    ).fetchone()
    assert row["order_name"] == "#1048"
    assert row["sku"] == "HM-LEG-M-BLK"
    assert row["blocked_po"] == "PO-2207"
    assert row["supplier_name"] == "Rhein Textil GmbH"
    assert row["issue_codes"] == "QTY_OVER,OVER_PO_VALUE"
    assert row["total_price"] == "79.00"
    blocked = conn.execute("SELECT ticket_id FROM gold_customer_service WHERE blocked_po IS NOT NULL").fetchall()
    assert [item["ticket_id"] for item in blocked] == [44021]
    decisions = dict(conn.execute("SELECT decision, COUNT(*) FROM bill_reviews GROUP BY decision"))
    assert decisions["INVESTIGATE"] == 1
    assert decisions["APPROVE"] == 2


def test_quellberg_queue_is_the_real_invoice_run(synced):
    _http, _settings, db, _stats = synced
    conn = connect(db)
    row = conn.execute(
        """
        SELECT COUNT(*),
               SUM(decision = 'INVESTIGATE'),
               SUM(decision = 'APPROVE'),
               ROUND(SUM(gross_eur), 2),
               SUM(gross_eur IS NULL)
        FROM ap_invoice_reviews
        """
    ).fetchone()
    assert tuple(row) == (16, 16, 0, 80472.4, 2)
    origin = conn.execute("SELECT DISTINCT origin FROM ap_invoice_reviews").fetchone()[0]
    assert origin == "invoice-review-agent"


def test_grounded_passes_and_does_not_write(synced):
    _http, settings, db, _stats = synced
    report = evaluate(db, settings, "grounded")
    assert report.failures == []
    assert report.passed == 6
    assert report.violations == 0
    hero = review_ticket(db, 44021, settings)
    assert hero.executed_writes == []
    assert "bis Sonntag" not in hero.reply_de
    assert "PO-2207" in hero.reply_de


def test_fraud_email_is_flagged_from_ticket_shop_and_email(synced):
    _http, settings, db, _stats = synced
    flagged = review_ticket(db, 44027, settings)
    sources = [item["source"] for item in flagged.fraud]
    assert flagged.intent == "fraud"
    assert sources == ["Zendesk", "Shopify", "Klaviyo"]
    assert flagged.executed_writes == []
    assert flagged.actions == ["do_not_pay_off_platform", "hand_to_human"]
    assert "nicht von uns" in flagged.reply_de
    assert "Paysafecard" in flagged.reply_de
    clean = review_ticket(db, 44021, settings)
    assert clean.fraud == []


def test_ungrounded_replies_fail_the_policy(synced):
    _http, settings, db, _stats = synced
    report = evaluate(db, settings, "ungrounded")
    assert report.passed == 0
    assert report.violations > 0
