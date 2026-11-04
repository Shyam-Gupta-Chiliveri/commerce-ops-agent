PRAGMA foreign_keys = ON;

CREATE TABLE shopify_orders (
  order_id INTEGER PRIMARY KEY,
  order_name TEXT NOT NULL,
  email TEXT NOT NULL,
  first_name TEXT,
  brand TEXT,
  created_at TEXT,
  financial_status TEXT,
  fulfillment_status TEXT,
  currency TEXT,
  total_price TEXT,
  promised_ship_date TEXT,
  delivered_at TEXT,
  tracking_number TEXT
);

CREATE TABLE shopify_line_items (
  line_id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL,
  sku TEXT NOT NULL,
  title TEXT,
  variant_title TEXT,
  quantity INTEGER,
  price TEXT
);

CREATE TABLE shopify_transactions (
  transaction_id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL,
  kind TEXT,
  status TEXT,
  amount TEXT,
  gateway TEXT,
  created_at TEXT
);

CREATE TABLE inventory (
  sku TEXT PRIMARY KEY,
  product_id TEXT,
  option_label TEXT,
  title TEXT,
  available INTEGER
);

CREATE TABLE zendesk_users (
  user_id INTEGER PRIMARY KEY,
  name TEXT,
  email TEXT,
  locale TEXT
);

CREATE TABLE zendesk_tickets (
  ticket_id INTEGER PRIMARY KEY,
  subject TEXT,
  status TEXT,
  brand TEXT,
  order_name TEXT,
  requester_id INTEGER,
  requester_email TEXT,
  first_name TEXT,
  created_at TEXT,
  description TEXT
);

CREATE TABLE zendesk_comments (
  comment_id INTEGER PRIMARY KEY,
  ticket_id INTEGER,
  author_id INTEGER,
  is_public INTEGER,
  body TEXT,
  created_at TEXT
);

CREATE TABLE klaviyo_events (
  event_id TEXT PRIMARY KEY,
  email TEXT,
  metric_name TEXT,
  happened_at TEXT,
  subject TEXT,
  campaign TEXT,
  order_name TEXT
);

CREATE TABLE anvyl_purchase_orders (
  po_id TEXT PRIMARY KEY,
  order_number TEXT,
  supplier_name TEXT,
  status TEXT,
  ships_on TEXT
);

CREATE TABLE anvyl_po_lines (
  po_id TEXT,
  sku TEXT,
  quantity REAL,
  quantity_received REAL,
  unit_price_micros INTEGER,
  PRIMARY KEY (po_id, sku)
);

CREATE TABLE sage_bills (
  bill_id TEXT PRIMARY KEY,
  po_number TEXT,
  vendor_name TEXT,
  sage_status TEXT,
  bill_date TEXT,
  reference TEXT,
  total_amount TEXT
);

CREATE TABLE sage_bill_lines (
  bill_id TEXT,
  sku TEXT,
  quantity REAL,
  unit_price TEXT,
  net_amount TEXT,
  PRIMARY KEY (bill_id, sku)
);

CREATE TABLE bill_reviews (
  bill_id TEXT PRIMARY KEY,
  po_number TEXT,
  decision TEXT,
  issue_codes TEXT,
  ordered_qty REAL,
  billed_qty REAL,
  ordered_net REAL,
  billed_net REAL
);

CREATE TABLE ap_invoice_reviews (
  source_file TEXT PRIMARY KEY,
  decision TEXT,
  priority TEXT,
  vendor TEXT,
  invoice_number TEXT,
  invoice_date TEXT,
  po TEXT,
  gross_eur REAL,
  issue_codes TEXT,
  summary TEXT,
  origin TEXT NOT NULL
);

CREATE VIEW gold_supply_block AS
SELECT
  po.order_number,
  po.supplier_name,
  pol.sku,
  pol.quantity AS ordered_qty,
  pol.quantity_received,
  br.decision,
  br.issue_codes,
  br.bill_id
FROM anvyl_po_lines pol
JOIN anvyl_purchase_orders po ON po.po_id = pol.po_id
LEFT JOIN bill_reviews br ON br.po_number = po.order_number
WHERE pol.quantity_received < pol.quantity
  AND br.decision = 'INVESTIGATE';

CREATE VIEW gold_customer_service AS
SELECT
  t.ticket_id,
  t.brand,
  t.order_name,
  t.requester_email,
  t.first_name,
  t.subject,
  t.status,
  o.financial_status,
  o.fulfillment_status,
  o.total_price,
  o.currency,
  li.sku,
  b.order_number AS blocked_po,
  b.supplier_name,
  b.issue_codes
FROM zendesk_tickets t
LEFT JOIN shopify_orders o ON o.order_name = t.order_name
LEFT JOIN shopify_line_items li ON li.order_id = o.order_id
LEFT JOIN gold_supply_block b ON b.sku = li.sku;
