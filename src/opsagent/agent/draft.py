from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from opsagent.settings import Settings
from opsagent.warehouse.queries import Event, Order, Stock, Supply, Ticket, Txn


@dataclass
class CaseFile:
    ticket: Ticket
    intent: str
    requested_size: str | None
    order: Order | None
    events: list[Event]
    supply: list[Supply]
    on_hand: int
    alternatives: list[Stock]
    requested_stock: Stock | None
    transactions: list[Txn]
    settings: Settings
    fraud: list[dict]

    @property
    def blocked(self) -> list[Supply]:
        return [row for row in self.supply if row.decision == "INVESTIGATE" and row.quantity_received < row.quantity]


def _day(value: str | None) -> str:
    return (value or "")[:10]


def _size_label(option: str) -> str:
    return option.split(" / ")[0]


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start[:10])).days


def grounded(case: CaseFile) -> tuple[str, str, list[str]]:
    if case.fraud or case.intent == "fraud":
        return _fraud(case)
    if case.order is None:
        de = (
            f"Hallo {case.ticket.first_name},\n\n"
            f"zu Ticket {case.ticket.ticket_id} finde ich keine Bestellung {case.ticket.order_name or ''} im Shop. "
            "Ich lege das einer Kollegin hin und rate den Status nicht.\n"
        )
        return de, "I cannot find this order in Shopify, so I will not guess.", ["hand_to_human"]
    if case.intent == "where_is_order":
        return _where_is(case)
    if case.intent == "refund":
        return _refund(case)
    if case.intent == "exchange_size":
        return _exchange(case)
    if case.intent == "double_charge":
        return _double(case)
    if case.intent == "product_complaint":
        return _complaint(case)
    if case.intent == "cancel_marketing":
        return _cancel(case)
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"ich habe Bestellung {case.order.order_name} gelesen und gebe das Ticket an eine Kollegin, "
        "weil das Anliegen nicht in den freigegebenen Fällen liegt.\n"
    )
    return de, "This intent is not in the approved set. A person takes it.", ["hand_to_human"]


def _where_is(case: CaseFile) -> tuple[str, str, list[str]]:
    order = case.order
    assert order is not None
    line = order.lines[0]
    block = case.blocked[0]
    delay = next((event for event in case.events if event.campaign == "Shipping delay"), None)
    late_days = _days(order.promised_ship_date, case.settings.as_of) if order.promised_ship_date else 0
    ranked = sorted(case.alternatives, key=lambda item: -item.available)
    alts = " oder ".join(f"Größe {_size_label(item.option_label)}, {item.available}" for item in ranked)
    alts_en = " or ".join(f"size {_size_label(item.option_label)} ({item.available} in stock)" for item in ranked)
    delay_sentence = "Dazu liegt keine Verzögerungsmail vor."
    delay_en = "There is no delay email on file."
    actions = ["offer_size_exchange", "offer_refund", "do_not_promise_date"]
    discount_sentence = "Einen Rabatt biete ich bei dieser Verspätung nicht an."
    discount_en = "I am not offering a discount for this delay"
    if late_days >= case.settings.delay_offer_after_days:
        actions.insert(0, "offer_wait_with_discount")
        discount_sentence = (
            f"warten und {case.settings.delay_discount_pct} % auf diese Bestellung erhalten, sobald sie das Lager verlässt"
        )
        discount_en = (
            f"wait, and receive {case.settings.delay_discount_pct}% on this order once it leaves the warehouse"
        )
    if delay is not None:
        delay_sentence = (
            f"Die Hinweis-Mail zur Verzögerung vom {_day(delay.happened_at)} hast du schon bekommen. "
            "Ich schicke sie nicht noch einmal."
        )
        delay_en = (
            f"You already received the delay email on {_day(delay.happened_at)}. I will not send it again."
        )
        actions.append("do_not_resend_delay_email")
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"danke für deine Nachricht zu Bestellung {order.order_name} ({line.title}, {line.variant_title}).\n\n"
        f"Im Shop steht die Bestellung auf bezahlt und noch nicht versendet. Ein Sendungscode liegt uns nicht vor. "
        f"Das zugesagte Versanddatum war der {order.promised_ship_date}. "
        f"Stand {case.settings.as_of} ist sie überfällig, und die bestellte Größe hat Bestand {case.on_hand}.\n\n"
        f"Die Nachlieferung hängt an {block.order_number} bei {block.supplier_name}. "
        f"Die Eingangsrechnung ist gesperrt ({block.issue_codes}), weil die berechnete Menge über der Bestellmenge liegt. "
        "Ich kann dir deshalb keinen Liefertermin zusagen.\n\n"
        f"Du kannst wählen: {discount_sentence}; wechseln auf {alts}; "
        f"oder den vollen Betrag von {order.total_price} {order.currency} zurückerhalten.\n\n"
        f"{delay_sentence}\n\n"
        "Sag mir, welche Möglichkeit du möchtest. Umsetzen tue ich das erst nach deiner Antwort.\n"
    )
    en = (
        f"Hello {case.ticket.first_name},\n\n"
        f"thank you for writing about order {order.order_name} ({line.title}, {line.variant_title}).\n\n"
        f"The shop shows the order as paid and not yet shipped. We do not have a tracking number. "
        f"The promised ship date was {order.promised_ship_date}. "
        f"As of {case.settings.as_of} it is overdue, and the size you ordered has {case.on_hand} in stock.\n\n"
        f"The replenishment is purchase order {block.order_number} with {block.supplier_name}. "
        f"The supplier bill is on hold ({block.issue_codes}) because the billed quantity is above the ordered quantity. "
        "I cannot promise a delivery date.\n\n"
        f"You can choose: {discount_en}; switch to {alts_en}; "
        f"or receive the full {order.total_price} {order.currency} back.\n\n"
        f"{delay_en}\n\n"
        "Tell me which option you want. I will not change the order until you reply.\n"
    )
    return de, en, actions


def _fraud(case: CaseFile) -> tuple[str, str, list[str]]:
    order_name = case.order.order_name if case.order else (case.ticket.order_name or "der genannten Bestellung")
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"die Mail zu {order_name}, die eine Gebühr oder einen Zahlencode verlangt, ist nicht von uns. "
        "Harbor nimmt keine Paysafecard und keine Zahlung außerhalb des Shops an.\n\n"
        "Bitte den Code nicht schicken und keinen Link aus der Mail öffnen. "
        "Ich lege das einer Kollegin hin und ändere die Bestellung nicht.\n"
    )
    en = (
        f"Hello {case.ticket.first_name},\n\n"
        f"the email about {order_name} that asks for a fee or a payment code is not from us. "
        "Harbor does not take Paysafecard or any payment outside the shop.\n\n"
        "Please do not send the code, and do not open a link from that email. "
        "I am leaving this with a colleague, and I will not change the order.\n"
    )
    return de, en, ["do_not_pay_off_platform", "hand_to_human"]


def _refund(case: CaseFile) -> tuple[str, str, list[str]]:
    order = case.order
    assert order is not None
    if order.financial_status == "refunded":
        refund_txn = next((txn for txn in case.transactions if txn.kind == "refund"), None)
        when = _day(refund_txn.created_at) if refund_txn else "dem hinterlegten Datum"
        when_en = _day(refund_txn.created_at) if refund_txn else "the date on file"
        de = (
            f"Hallo {case.ticket.first_name},\n\n"
            f"Bestellung {order.order_name} ist bereits erstattet. "
            f"Der Zahlstatus ist refunded, Betrag {order.total_price} {order.currency}. "
            f"Die Rückbuchung im Shop ist vom {when}.\n\n"
            "Ich löse keine zweite Erstattung aus. Wenn der Betrag auf dem Kontoauszug fehlt, "
            "prüfe bitte die Karte, mit der du bezahlt hast. Wenn er dort auch nicht ankommt, "
            "antworte kurz, dann gibt das Payment-Team den Fall weiter.\n"
        )
        en = (
            f"Hello {case.ticket.first_name},\n\n"
            f"order {order.order_name} has already been refunded. "
            f"The payment status is refunded, amount {order.total_price} {order.currency}. "
            f"The refund in the shop is dated {when_en}.\n\n"
            "I will not issue a second refund. If the amount is missing from your statement, "
            "please check the card you paid with. If it is not there either, reply and the payments team will take it from here.\n"
        )
        return de, en, ["do_not_refund_again", "escalate_if_payout_missing"]
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"Bestellung {order.order_name} ist im Shop noch nicht erstattet (Zahlstatus {order.financial_status}). "
        "Ich stoße die Erstattung nicht automatisch an. Eine Kollegin prüft die Retoure und macht das dann.\n"
    )
    return de, "Refund is not on the order yet. A person has to confirm it.", ["wait_for_human_refund"]


def _exchange(case: CaseFile) -> tuple[str, str, list[str]]:
    order = case.order
    assert order is not None
    line = order.lines[0]
    within = False
    if order.delivered_at:
        within = _days(order.delivered_at, case.settings.as_of) <= case.settings.return_window_days
    stock = case.requested_stock
    if within and stock and stock.available > 0:
        de = (
            f"Hallo {case.ticket.first_name},\n\n"
            f"Bestellung {order.order_name} ({line.title}, Größe {line.variant_title}) wurde geliefert. "
            f"Ein Umtausch auf Größe {case.requested_size}, {stock.available} ist möglich: "
            f"die Retourenfrist von {case.settings.return_window_days} Tagen ist offen, und die Größe ist auf Lager.\n\n"
            "Schick die gelieferte Größe zurück. Die neue Größe geht raus, sobald die Retoure gebucht ist. "
            "Eine Erstattung löse ich nicht aus, solange du den Umtausch möchtest. "
            "Das Retourenlabel lege ich erst an, wenn du den Umtausch bestätigst.\n"
        )
        en = (
            f"Hello {case.ticket.first_name},\n\n"
            f"order {order.order_name} ({line.title}, size {line.variant_title}) has been delivered. "
            f"An exchange to size {case.requested_size} is possible: {stock.available} are in stock, "
            f"and the {case.settings.return_window_days}-day return window is still open.\n\n"
            "Send the delivered size back. The new size goes out once the return is booked. "
            "I will not refund while you want the exchange, and I will not create the return label until you confirm.\n"
        )
        return de, en, ["offer_exchange", "wait_for_customer_confirm"]
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"einen Umtausch zu Bestellung {order.order_name} kann ich so nicht anbieten. "
        "Ich gebe das Ticket an eine Kollegin und lege kein Label an.\n"
    )
    return de, "Exchange conditions are not met. A person takes the ticket.", ["hand_to_human"]


def _double(case: CaseFile) -> tuple[str, str, list[str]]:
    order = case.order
    assert order is not None
    sales = [txn for txn in case.transactions if txn.kind == "sale"]
    if len(sales) == 1:
        de = (
            f"Hallo {case.ticket.first_name},\n\n"
            f"ich habe Bestellung {order.order_name} geprüft. Im Shop sehe ich genau eine Zahlung "
            f"über {sales[0].amount} {order.currency} am {_day(sales[0].created_at)}, Zahlstatus {order.financial_status}. "
            "Einen zweiten Auftrag oder eine zweite Abbuchung sehe ich dort nicht.\n\n"
            "Ob deine Bank eine zweite Buchung anzeigt, kann ich aus Shopify nicht belegen. "
            "Ich gebe das an das Payment-Team und bestätige dir keine Doppelabbuchung, die in der Bestellung nicht steht.\n"
        )
        en = (
            f"Hello {case.ticket.first_name},\n\n"
            f"I checked order {order.order_name}. The shop shows exactly one payment "
            f"of {sales[0].amount} {order.currency} on {_day(sales[0].created_at)}, status {order.financial_status}. "
            "I do not see a second order or a second charge there.\n\n"
            "I cannot see from the shop whether your bank shows another posting. "
            "I am handing this to the payments team, and I will not confirm a double charge that is not on the order.\n"
        )
        return de, en, ["escalate_payments", "do_not_confirm_double_charge"]
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"zu Bestellung {order.order_name} sehe ich {len(sales)} erfolgreiche Zahlungen. "
        "Das prüft das Payment-Team, ich erstatte von hier aus nichts.\n"
    )
    return de, "More than one sale is on the order. Payments investigates, nothing is refunded here.", ["escalate_payments"]


def _complaint(case: CaseFile) -> tuple[str, str, list[str]]:
    order = case.order
    assert order is not None
    line = order.lines[0]
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"es tut mir leid, dass {line.title} aus Bestellung {order.order_name} nicht gehalten hat.\n\n"
        "Ich darf dir dazu keinen medizinischen Rat geben. Wenn du Schmerzen oder eine Hautreizung hast, "
        "wende dich bitte an eine Ärztin oder einen Arzt. "
        f"Aus dem Shop kann ich einen Ersatz anbieten (Bestand {case.on_hand}) "
        f"oder den Betrag von {order.total_price} {order.currency} erstatten. "
        "Was davon passiert, setzt eine Kollegin um, nachdem du dich entschieden hast.\n"
    )
    en = (
        f"Hello {case.ticket.first_name},\n\n"
        f"I am sorry that the {line.title} from order {order.order_name} did not hold up.\n\n"
        "I cannot give you medical advice. If you have pain or a skin irritation, please speak to a doctor. "
        f"From the shop I can offer a replacement ({case.on_hand} in stock) "
        f"or a refund of {order.total_price} {order.currency}. "
        "A colleague will do whichever you choose, after you decide.\n"
    )
    return de, en, ["offer_replacement_or_refund", "no_medical_advice", "wait_for_customer_confirm"]


def _cancel(case: CaseFile) -> tuple[str, str, list[str]]:
    order = case.order
    assert order is not None
    winback = next((event for event in case.events if event.campaign == "Winback"), None)
    seen = f" Im Profil liegt eine Winback-Mail vom {_day(winback.happened_at)}." if winback else ""
    seen_en = f" The profile has a winback email from {_day(winback.happened_at)}." if winback else ""
    de = (
        f"Hallo {case.ticket.first_name},\n\n"
        f"Bestellung {order.order_name} bleibt, wie sie ist. Sie wurde geliefert, ich storniere sie nicht.\n\n"
        f"Du möchtest keine weiteren Kampagnenmails.{seen} "
        "Die Abmeldung ist eine Schreibaktion im Marketing-Tool. Die führe ich nicht selbst aus. "
        "Ich lege sie einer Kollegin hin, die den Versand stoppt.\n"
    )
    en = (
        f"Hello {case.ticket.first_name},\n\n"
        f"order {order.order_name} stays as it is. It was delivered, and I will not cancel it.\n\n"
        f"You do not want further campaign emails.{seen_en} "
        "Unsubscribing is a write in the marketing tool. I do not do that myself. "
        "I am leaving it with a colleague, who will stop the emails.\n"
    )
    return de, en, ["keep_order", "queue_marketing_suppression"]


def ungrounded(case: CaseFile) -> tuple[str, str, list[str]]:
    """What a reply looks like when it uses only the ticket text."""
    text = f"{case.ticket.subject}\n{case.ticket.description}".lower()
    if "sonntag" in text:
        reply = "Deine Bestellung kommt am Sonntag. Sendungsnummer: 1Z999."
    elif "zweimal" in text:
        reply = "Ja, du wurdest doppelt abgebucht, ich erstatte die zweite Zahlung."
    elif "ausgelaufen" in text:
        reply = "Das ist medizinisch unbedenklich und kein Gesundheitsrisiko."
    elif "keine mails" in text or "newsletter" in text:
        reply = "Ich habe dich abgemeldet und die Bestellung ist storniert."
    elif "größe" in text:
        reply = "Ich erstatte dir sofort."
    elif "erstatt" in text or "geld" in text:
        reply = "Ich leite die Erstattung ein."
    else:
        reply = "Wir kümmern uns."
    return reply, reply, ["send_reply_without_tools"]


def critique(case: CaseFile, reply: str) -> list[str]:
    findings: list[str] = []
    if case.order and case.order.order_name not in reply:
        findings.append("order name missing")
    if case.order and not case.order.tracking_number and "Sendungsnummer:" in reply:
        findings.append("tracking invented")
    if case.intent == "where_is_order":
        for phrase in ("bis Sonntag", "kommt am Sonntag", "garantiert"):
            if phrase in reply:
                findings.append("promised a date")
        for block in case.blocked:
            if block.order_number not in reply:
                findings.append("purchase order missing")
    if case.intent == "refund" and case.order and case.order.financial_status == "refunded":
        if "ich leite die Erstattung ein" in reply:
            findings.append("second refund")
    if case.intent == "double_charge" and "Ja, du wurdest doppelt" in reply:
        findings.append("confirmed double charge")
    if case.intent == "product_complaint" and ("medizinisch unbedenklich" in reply or "kein Gesundheitsrisiko" in reply):
        findings.append("medical claim")
    if case.intent == "cancel_marketing" and ("ich habe dich abgemeldet" in reply or "Bestellung ist storniert" in reply):
        findings.append("write action claimed")
    if case.intent == "exchange_size" and "Ich erstatte dir sofort" in reply:
        findings.append("refund instead of exchange")
    return findings
