# Commerce ops agent

**Live:** [https://ops.138.2.179.154.sslip.io/](https://ops.138.2.179.154.sslip.io/) — the same page as the local prototype, served by Docker on the Oracle VM.

A small, runnable version of the pipeline in the SNOCKS Junior AI Engineer posting: pull Shopify, Zendesk, Klaviyo, Anvyl and Sage over REST, land them in a warehouse, and let an agent answer customer-service tickets from those rows. Quality is measured. Nothing is written back to the source systems.

Harbor House, the shop in the fixtures, is fictional. It is not SNOCKS data and it is not a former employer's data. The 16 supplier invoices are the real output of [invoice-review-agent](https://github.com/Shyam-Gupta-Chiliveri/invoice-review-agent), copied into `fixtures/quellberg/results.csv`.

## Run

```bash
cd ~/Desktop/commerce-ops-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m opsagent demo
pytest -q
```

`demo` prints the report, the eval, and the reply for ticket 44021. The business clock is frozen at 2026-11-04, so the same commands give the same result tomorrow.

`python -m opsagent serve` starts the fixture APIs on http://127.0.0.1:8091. A Shopify page, with the fixture token:

```bash
curl -s -H "X-Shopify-Access-Token: shpat_demo" \
  "http://127.0.0.1:8091/admin/api/2024-10/orders.json?limit=2"
```

The `Link` header on that response is the next page. The client follows it and does not parse the cursor.

## The ticket to walk through

Ticket 44021, Lena, Harbor Move, order #1048. She needs the leggings before Sunday.

The warehouse join `gold_customer_service` is the whole point:

- Shopify: paid, not fulfilled, SKU `HM-LEG-M-BLK`, stock 0, no tracking number, promised ship date 2026-10-24.
- Anvyl: PO-2207 at Rhein Textil, 400 ordered, 0 received. Unit price is stored as micros: 12.00 EUR is `12000000`.
- Sage: bill BILL-2207 charges 480 at the same unit price. `rules.py` marks it `INVESTIGATE` / `QTY_OVER,OVER_PO_VALUE`. Sage itself only knows the bill is `UNPAID`. The pay-or-not decision is ours, in code, same idea as the receipt agent.
- Klaviyo: a "Shipping delay" email already went out on 2026-10-28, so the reply does not send another one.
- The public reply offers wait plus 15%, a size that is in stock, or a refund of 79.00 EUR. It does not promise Sunday. Nothing is executed until she answers, and even then a person confirms. `executed_writes` is empty.

## What each system is for

Shopify is the shop. Orders, payments, fulfilments, inventory. This client uses the Admin REST API, version `2024-10`, header `X-Shopify-Access-Token`. List endpoints page with an opaque `page_info` cursor in the `Link` header. A real double-charge check is `GET /orders/{id}/transactions.json`: kind `sale`, status `success`. One sale means the shop cannot confirm a second charge. Inventory in production is two calls, variant to `inventory_item_id`, then inventory levels by location. The fixture returns both in a shortened form.

Zendesk is a support desk: tickets, users, comments. Auth is Basic, `{email}/token:{api_token}`. Collections return `next_page` until it is null. The posting also names Resolvia. SNOCKS has publicly reviewed Resolvia, the Shopify helpdesk app, as their support tool. Resolvia's API is not this client. A Resolvia adapter would fill the same `zendesk_tickets` table. The agent does not change.

Klaviyo is the customer messaging record: placed order, fulfilled, refunded, and which campaign email was already sent. Every call needs `Authorization: Klaviyo-API-Key ...` and a `revision` header. Collections page with `links.next`. The revision pinned here is `2025-04-15`; a live account needs a revision Klaviyo still accepts. This project only reads. Suppressing a winback flow is a write, and the agent queues it for a person.

Anvyl is Sage Supply Chain Intelligence. Purchase orders live at `GET https://api.anvyl.com/api/v1/teams/{team_id}/purchase_orders`. The API key goes in `Authorization` without the word Bearer. Pages use `page` and `per_page`, and the counts come back in `X-Total-Pages`. Order items carry `quantity` and `unit_price_micros`. In this fixture, `sku` and `quantity_received` are already filled in. Live, the SKU comes from the part record and the received quantity from shipments.

Sage Business Cloud Accounting stores the supplier invoice. `GET https://api.accounting.sage.com/v3.1/purchase_invoices`, OAuth Bearer plus the `X-Business` header, and a `$next` link for the next page. The fixture is a reduced purchase-invoice payload. Sage Intacct is a different product with a different API. Ask which one the team actually runs before naming a base URL in production.

## How a sync is shaped

Bronze is the raw JSON each client returns, written to `var/bronze/` by the demo. Silver is the SQLite tables in `schema.sql`. Gold is the views, above all `gold_customer_service`, which is the "one customer, one row" report. The agent reads gold and silver. It does not call the APIs again while drafting, so the reply and the SQL report cannot disagree.

Pagination is different on purpose, and each client follows that vendor's style:

| System | How the next page works | Pages in the demo |
| --- | --- | --- |
| Shopify | `Link` header, opaque cursor | 4 for 7 orders |
| Zendesk | `next_page` URL | 4 for 7 tickets |
| Klaviyo | `links.next` | 5 for 9 events |
| Anvyl | `X-Total-Pages` | 2 for 3 purchase orders |
| Sage | `$next` | 2 for 3 bills |

A 429 is retried with `Retry-After`. Shopify webhooks are checked with `X-Shopify-Hmac-Sha256` in `security.py`. The demo does not depend on a webhook arriving.

## Measurement

`fixtures/eval_cases.json` is the spec for six tickets: where is my order, refund already paid, size exchange, claimed double charge, a product complaint, and "stop the emails".

The grounded drafter passes 6/6 tickets and 53/53 checks, with 0 policy violations. The ungrounded drafter, which answers from the ticket text alone, passes 0/6 and raises 20 violations, including a promised Sunday and an invented tracking number. Model cost is EUR 0 in both rows because no model is called. A Claude or OpenAI call would be another function with the same signature, and the critic in `draft.py` would still have to pass before a person sends the text. The decision to refund, exchange, or block a bill is not left to the model. That is the same split as the receipt agent: the model may word the answer, the rule decides.

## Map to the posting

- AI automation from prototype to something you can run: `python -m opsagent demo`, Dockerfile, pytest, GitHub Actions.
- APIs into a warehouse the agent can use: the five clients, then `gold_customer_service`.
- Customer service, supply chain, and reporting in one place: the six tickets, the Anvyl/Sage block on #1048, and the Quellberg invoice queue.
- Quality, cost, latency: the eval table. Latency on this fixture is under a millisecond because there is no model call. That number is only meaningful next to the 0 violations. A live model would add seconds and a per-ticket cost, which is why the critic stays outside the model.
- Several projects at once, with a person still in the loop: the agent proposes actions and executes none.

## What not to claim

These fixture orders are not the Shopify shop from HCL, and they are not SNOCKS production. The HCL integration named on the CV was internal. This repository is the same pattern, rebuilt so it can be opened, tested, and measured. If a question is about that older system, answer from what you actually remember of it. The numbers above belong to this repo.
