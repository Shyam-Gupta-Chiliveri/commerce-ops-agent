"""Local page for the one agent that reads Shopify, Zendesk, Klaviyo, Anvyl and Sage."""

from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from opsagent.agent.copilot import review_ticket
from opsagent.eval.run import evaluate
from opsagent.mockapi.app import create_app
from opsagent.paths import VAR_DIR
from opsagent.settings import Settings, load_settings
from opsagent.sync_asgi import SyncASGITransport
from opsagent.warehouse.load import sync
from opsagent.warehouse.queries import connect

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commerce ops agent</title>
<style>
  :root { color-scheme: light; --ink: #1c1915; --muted: #5c564c; --line: #e4ddd2; --paper: #f7f4ee; --card: #fff; --accent: #9a3412; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 16px/1.45 "Iowan Old Style", Palatino, Georgia, serif; color: var(--ink); background: var(--paper); }
  header { padding: 28px 32px 18px; border-bottom: 1px solid var(--line); }
  h1 { font-size: 28px; font-weight: 600; margin: 0 0 6px; letter-spacing: -0.02em; }
  .sub { color: var(--muted); margin: 0; }
  .pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .pill { font: 13px/1 ui-sans-serif, system-ui, sans-serif; background: #fff; border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; }
  main { display: grid; grid-template-columns: 320px 1fr; min-height: calc(100vh - 140px); }
  aside { border-right: 1px solid var(--line); padding: 12px; }
  button.ticket { display: block; width: 100%; text-align: left; background: transparent; border: 0; border-radius: 10px; padding: 12px; cursor: pointer; font: inherit; color: inherit; }
  button.ticket strong { display: block; font-size: 15px; }
  button.ticket span { color: var(--muted); font-size: 14px; }
  button.ticket[aria-pressed="true"] { background: #fff; outline: 1px solid var(--line); }
  section { padding: 28px 32px 48px; max-width: 820px; }
  .meta { font: 13px/1.4 ui-sans-serif, system-ui, sans-serif; color: var(--muted); margin-bottom: 14px; }
  .reply { white-space: pre-wrap; background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 20px 22px; margin: 0 0 16px; }
  .note { white-space: pre-wrap; font: 14px/1.45 ui-sans-serif, system-ui, sans-serif; color: var(--muted); }
  h2 { font-size: 13px; font-weight: 650; letter-spacing: 0.04em; text-transform: uppercase; margin: 22px 0 8px; }
  @media (max-width: 800px) { main { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid var(--line); } }
</style>
</head>
<body>
<header>
  <h1>Commerce ops agent</h1>
  <p class="sub">One agent. Shopify, Zendesk, Klaviyo, Anvyl and Sage are already in the warehouse before it writes a reply.</p>
  <div class="pills" id="pills"></div>
</header>
<main>
  <aside id="list"></aside>
  <section id="detail"><p class="sub">Loading tickets…</p></section>
</main>
<script>
const list = document.querySelector("#list");
const detail = document.querySelector("#detail");
const pills = document.querySelector("#pills");

function esc(value) {
  return String(value ?? "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

async function loadSummary() {
  const summary = await (await fetch("/api/summary")).json();
  pills.innerHTML = [
    ["Shopify", summary.shopify_orders + " orders"],
    ["Zendesk", summary.zendesk_tickets + " tickets"],
    ["Klaviyo", summary.klaviyo_events + " events"],
    ["Anvyl", summary.anvyl_orders + " purchase orders"],
    ["Sage", summary.sage_bills + " bills"],
    ["Grounded replies", summary.grounded_passed + "/" + summary.grounded_total],
  ].map(([name, value]) => `<span class="pill"><strong>${esc(name)}</strong> ${esc(value)}</span>`).join("");
}

function render(ticket) {
  detail.innerHTML = `
    <div class="meta">${esc(ticket.brand)} · ${esc(ticket.intent)} · writes executed: none</div>
    <h2>Reply</h2>
    <div class="reply">${esc(ticket.reply_de)}</div>
    <h2>Internal note</h2>
    <div class="note">${esc(ticket.internal_note)}</div>`;
}

async function openTicket(id, button) {
  for (const node of list.querySelectorAll("button")) node.setAttribute("aria-pressed", "false");
  if (button) button.setAttribute("aria-pressed", "true");
  const ticket = await (await fetch("/api/tickets/" + id)).json();
  render(ticket);
}

async function main() {
  await loadSummary();
  const tickets = await (await fetch("/api/tickets")).json();
  list.innerHTML = "";
  for (const ticket of tickets) {
    const button = document.createElement("button");
    button.className = "ticket";
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.innerHTML = `<strong>${esc(ticket.first_name)} · ${esc(ticket.order_name)}</strong><span>${esc(ticket.subject)}</span>`;
    button.addEventListener("click", () => openTicket(ticket.ticket_id, button));
    list.appendChild(button);
    if (ticket.ticket_id === 44021) openTicket(ticket.ticket_id, button);
  }
}
main();
</script>
</body>
</html>
"""


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

    @app.get("/api/tickets")
    def tickets():
        conn = connect(db)
        try:
            rows = conn.execute(
                """
                SELECT ticket_id, subject, brand, order_name, first_name
                FROM zendesk_tickets
                ORDER BY ticket_id
                """
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]

    @app.get("/api/tickets/{ticket_id}")
    def ticket(ticket_id: int):
        try:
            result = review_ticket(db, ticket_id, settings)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown ticket") from exc
        conn = connect(db)
        try:
            row = conn.execute("SELECT brand FROM zendesk_tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        finally:
            conn.close()
        return {
            "ticket_id": result.ticket_id,
            "brand": row["brand"] if row else "",
            "intent": result.intent,
            "actions": result.actions,
            "reply_de": result.reply_de,
            "reply_en": result.reply_en,
            "internal_note": result.internal_note,
            "critic": result.critic,
            "executed_writes": result.executed_writes,
        }

    return app
