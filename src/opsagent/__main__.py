from __future__ import annotations

import argparse
import os

import httpx
import uvicorn

from opsagent.agent.copilot import review_ticket
from opsagent.eval.run import evaluate, format_eval, write_eval_json
from opsagent.mockapi.app import create_app
from opsagent.prototype import create_prototype
from opsagent.paths import VAR_DIR
from opsagent.reporting.report import render_report
from opsagent.settings import load_settings
from opsagent.sync_asgi import SyncASGITransport
from opsagent.warehouse.load import sync


def _client(settings):
    app = create_app(settings)
    http = httpx.Client(transport=SyncASGITransport(app), base_url="http://mock")
    return app, http


def _run_sync(settings, http):
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    return sync(http, settings, VAR_DIR / "warehouse.sqlite", VAR_DIR / "bronze")


def cmd_demo() -> None:
    settings = load_settings()
    _app, http = _client(settings)
    stats = _run_sync(settings, http)
    db = VAR_DIR / "warehouse.sqlite"
    grounded = evaluate(db, settings, "grounded")
    ungrounded = evaluate(db, settings, "ungrounded")
    report = render_report(db, stats, [grounded, ungrounded])
    (VAR_DIR / "report.md").write_text(report, encoding="utf-8")
    write_eval_json(VAR_DIR / "eval.json", [grounded, ungrounded])
    hero = review_ticket(db, 44021, settings)
    print(report)
    print(format_eval(grounded))
    print(format_eval(ungrounded))
    print("\n--- Ticket 44021, public reply ---\n")
    print(hero.reply_de)
    print("--- internal note ---\n")
    print(hero.internal_note)


def cmd_ticket(ticket_id: int) -> None:
    settings = load_settings()
    _app, http = _client(settings)
    _run_sync(settings, http)
    result = review_ticket(VAR_DIR / "warehouse.sqlite", ticket_id, settings)
    print(result.reply_de)
    print(result.internal_note)
    print(f"intent {result.intent}")
    print(f"actions {', '.join(result.actions)}")
    print(f"critic {result.critic or 'ok'}")
    print(f"writes {result.executed_writes or 'none'}")


def cmd_eval() -> None:
    settings = load_settings()
    _app, http = _client(settings)
    _run_sync(settings, http)
    db = VAR_DIR / "warehouse.sqlite"
    for name in ("grounded", "ungrounded"):
        print(format_eval(evaluate(db, settings, name)))


def cmd_serve() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8091)


def cmd_prototype() -> None:
    host = os.getenv("OPSAGENT_HOST", "127.0.0.1")
    port = int(os.getenv("OPSAGENT_PORT", "8092"))
    uvicorn.run(create_prototype(load_settings()), host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="opsagent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    sub.add_parser("eval")
    sub.add_parser("serve")
    sub.add_parser("prototype")
    ticket = sub.add_parser("ticket")
    ticket.add_argument("ticket_id", type=int)
    args = parser.parse_args(argv)
    if args.cmd == "demo":
        cmd_demo()
    elif args.cmd == "eval":
        cmd_eval()
    elif args.cmd == "serve":
        cmd_serve()
    elif args.cmd == "prototype":
        cmd_prototype()
    elif args.cmd == "ticket":
        cmd_ticket(args.ticket_id)


if __name__ == "__main__":
    main()
