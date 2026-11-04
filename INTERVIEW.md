# Gespräch mit Justin, Freitag 6. November, 14:00–14:45

Justin ist Automation Engineer. Er will sehen, ob du einen Prozess über mehrere Systeme lesen kannst, ob die Antwort an den Zahlen hängt, und ob du sagst, wo die Automatisierung aufhört. Deutsch oder Englisch ist beides in Ordnung. Die Mail von Jana ist Deutsch, sein Name ist Englisch. Fang auf Deutsch an. Wenn er wechselt, wechsel mit.

Öffne das Projekt, bevor du in den Call gehst:

```bash
cd ~/Desktop/commerce-ops-agent
source .venv/bin/activate
python -m opsagent demo
```

Die Zahlen, die du auswendig kannst:

- 6 Tickets, grounded 6/6, 53/53 Checks, 0 Verstöße, Modellkosten 0 Euro.
- Dieselbe Prüfung ohne die Warehouse-Daten: 0/6, 20 Verstöße.
- Shopify 7 Bestellungen in 4 Seiten, Zendesk 7 Tickets in 4 Seiten, Klaviyo 9 Events in 5 Seiten, Anvyl 3 Bestellungen in 2 Seiten, Sage 3 Rechnungen in 2 Seiten.
- Ticket 44021, Bestellung #1048, 79,00 Euro, Bestand 0, PO-2207, Rhein Textil, Rechnung 480 statt 400, Codes `QTY_OVER` und `OVER_PO_VALUE`.
- Klaviyo-Mail „Shipping delay“ am 2026-10-28, also nicht noch einmal schicken.
- Die 16 Belege aus dem Invoice-Review-Agent: 16 investigate, 0 approve, 80.472,40 Euro auf den Belegen mit Betrag, 2 ohne Betrag. Doppelt gezählt ist die Kolb-Rechnung, bis ein Mensch sie rausnimmt.

## Die ersten zwei Minuten

„Ich habe die Stelle so gelesen: Interne Automationen für Customer Service, Supply Chain und Reporting. Systeme per API ins Warehouse, und der Agent arbeitet auf diesen Daten, nicht auf einem Prompt allein. Gemessen wird Qualität, Kosten und Latenz.

Das Repo ist genau dieser Schnitt, mit Fixture-Daten einer erfundenen Marke Harbor House. Live-Zugänge zu euren Shops habe ich nicht, und ich wollte keine erfundenen SNOCKS-Tickets bauen. Die Lieferantenrechnungen unten im Report sind echt: das ist der Lauf meines Invoice-Review-Agents, 16 Belege, keine Freigabe.

Der eine Fall, den ich zeigen will, ist Ticket 44021.“

Dann `python -m opsagent ticket 44021` oder die Stelle im Demo-Output. Lies die Antwort nicht vor. Zeig die vier Fakten und die eine Grenze:

1. Shopify: bezahlt, nicht versendet, kein Sendungscode, Bestand 0.
2. Anvyl PO-2207: nichts eingebucht.
3. Sage-Rechnung: Menge 480 gegen Bestellung 400, deshalb `INVESTIGATE`. Die Entscheidung steht nicht in Sage. Die macht `rules.py`. Sage kennt die Rechnung als `UNPAID`.
4. Klaviyo: die Verzögerungsmail ist raus. Keine zweite.
5. Grenze: kein Termin bis Sonntag, keine Erstattung und kein Größentausch, bevor Lena sich entscheidet, und auch dann führt das ein Mensch aus. `executed_writes` ist leer.

Der Satz, der den Job trifft: „Das Ticket ist das Symptom. Die Ursache liegt in der Lieferantenrechnung. Wer nur Zendesk liest, verspricht einen Termin, den das Lager nicht halten kann.“

## Wenn er in den Code will

- Connectoren: `src/opsagent/connectors/`. Jede Datei macht nur HTTP und die Pagination dieses Anbieters. Shopify folgt dem `Link`-Header und liest `page_info` nicht aus. Zendesk folgt `next_page`. Klaviyo folgt `links.next` und schickt den `revision`-Header. Anvyl liest `X-Total-Pages`. Sage bricht ab, wenn `$next` leer ist.
- Warehouse: `src/opsagent/warehouse/schema.sql`, View `gold_customer_service`. Bronze liegt nach dem Demo unter `var/bronze/`.
- Entscheidung über die Rechnung: `src/opsagent/rules.py`. Kein Modell.
- Antwort und Critic: `src/opsagent/agent/draft.py`.
- Messung: `fixtures/eval_cases.json` und `src/opsagent/eval/run.py`.
- Tests: `pytest -q` → 11 passed.

## Was die Systeme bei euch tun

Shopify ist der Shop: Bestellung, Zahlung, Fulfillment, Bestand. Admin REST, Header `X-Shopify-Access-Token`, Version im Pfad, bei mir `2024-10`. Eine Doppelabbuchung prüft man über die Transactions der Bestellung, nicht über den Tickettext. Eine erfolgreiche `sale` heißt: im Shop ist eine Zahlung. Was die Bank zeigt, sieht Shopify nicht. Das ist Ticket 44024.

Zendesk ist das Ticket-System im Beispiel der Stelle. Auth ist Basic mit `email/token:api_token`. Ihr setzt öffentlich auf Resolvia, die Shopify-Helpdesk-App. Mein Client spricht die Zendesk-Form, weil die öffentlich und stabil ist. Resolvia wäre ein zweiter Adapter in dieselben Tabellen. Den Resolvia-Vertrag kenne ich nicht, den würde ich an Tag eins mit einem Read-only-Key gegen die Doku prüfen, bevor ich ein Feld erfinde.

Klaviyo ist die Kundenkommunikation: Placed Order, Fulfilled, Refunded, und welche Kampagne schon gesendet wurde. Ohne `revision`-Header antwortet die API mit 400. Ich lese nur. Abmelden ist ein Schreibzugriff und bleibt bei einem Menschen. Das ist Ticket 44026.

Anvyl ist Sage Supply Chain Intelligence. Purchase Orders unter `https://api.anvyl.com/api/v1/teams/{team_id}/purchase_orders`. Der Key steht direkt im `Authorization`-Header, ohne das Wort Bearer. Preis in Micros: 12 Euro sind `12000000`. SKU und empfangene Menge habe ich im Fixture schon aufgelöst. Live kommen die von Part und Shipment, nicht aus dem Create-Payload.

Sage Accounting ist die Eingangsrechnung: `GET /v3.1/purchase_invoices`, Bearer plus Header `X-Business`. Sage Intacct ist ein anderes Produkt. Ich würde fragen, welches von beiden bei euch läuft.

## Fünf Fragen, die kommen können

**Warum kein LLM in der Entscheidung?** Weil eine Erstattung und eine gesperrte Rechnung reproduzierbar sein müssen. Der Critic ist Code. Ein Modell darf den Ton formulieren, aber nur durch dieselbe Prüfung. Der ungrounded Drafter zeigt den Fehler, wenn man nur den Tickettext nimmt: Zusage für Sonntag, erfundene Sendungsnummer, zweite Erstattung, medizinische Aussage. 0 von 6.

**Warum sind die Modellkosten 0?** Weil in diesem Lauf kein Modell aufgerufen wird. Die Latenz von 0,2 ms ist die Warehouse-Antwort, nicht eine Modellantwort. Sobald ein Modell dazukommt, messe ich dieselben Checks plus Tokens und Zeit. Im RAG-Projekt lag ich bei etwa 0,002 Dollar und 2 bis 5 Sekunden. Dieselbe Messart, anderer Use Case. Die 0,2 ms würde ich nicht als Modellantwort verkaufen.

**Shopify-Bestand?** Zwei Schritte live: Variante zur `inventory_item_id`, dann Levels pro Location. Das Fixture liefert beides verkürzt. Ich würde nicht so tun, als wäre `available` ein einzelnes Shopify-Feld auf der Bestellung.

**Webhook oder Poll?** Für Bestellungen ein Webhook, Signatur `X-Shopify-Hmac-Sha256`, sonst verpasst man die Black Week und pollt sich in ein Rate Limit. Der nächtliche Sync bleibt, weil ein verpasster Webhook sonst eine Lücke lässt. 429 mit `Retry-After` ist im Client. Der Test dazu ist `test_retries_429`.

**Was automatisierst du nicht?** Geld raus, Bestand buchen, Marketing abmelden, medizinischen Rat, einen Liefertermin, den die PO nicht hergibt. Der Agent schlägt die Aktion vor. Ein Mensch bestätigt. Wenn das Modell oder die API ausfällt, geht das Ticket an den Menschen, es wird nicht geraten. Dieselbe Regel wie bei den Belegen: im Zweifel `INVESTIGATE`, nie automatisch bezahlen.

## Wenn er nach HCL fragt

Die Shopify-, Zendesk-, Klaviyo- und Sage-Anbindung im Lebenslauf war intern. Diesen Code konnte ich nicht mitnehmen. Dieses Repo ist dasselbe Muster, neu gebaut, damit man es aufmachen und messen kann. Die Harbor-House-Zeilen sind Fixtures vom November 2026. Sie sind nicht der alte Kundenmandant. Zahlen, die du nicht aus diesem Lauf oder aus deiner Erinnerung hast, nicht erfinden.

## Wenn die Zeit für einen zweiten Fall reicht

Ticket 44024, angebliche Doppelabbuchung. Shopify zeigt eine `sale` über 64,00 Euro. Die Antwort bestätigt die zweite Abbuchung nicht und gibt sie an Payments. Das ist der Punkt „ehrlich sagen, wo die Daten aufhören“.

Ticket 44025, Periodenunterwäsche. Ersatz oder Erstattung, kein medizinischer Rat. Zeigt, dass der Critic mehr kann als Beträge prüfen.
