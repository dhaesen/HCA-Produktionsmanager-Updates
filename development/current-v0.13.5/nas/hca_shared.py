from __future__ import annotations

import asyncio
import base64
import csv
import io
import csv
import io
import json
import os
import mimetypes
import smtplib
import imaplib
import email
from email import policy as email_policy
from email.header import decode_header
from email.message import EmailMessage
import hashlib
import html as html_lib
import secrets
import re
import sqlite3
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response, HTMLResponse

router = APIRouter(prefix="/api/hca-shared", tags=["hca-shared"])

DATA_DIR = Path(os.getenv("HCA_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "hca_shared.sqlite3"
LABEL_DIR = DATA_DIR / "hca_shipping_labels"
SENDCLOUD_BASE = "https://panel.sendcloud.sc/api/v3"
INTERNAL_BASE = "http://127.0.0.1:8787"
BASE_DB_PATH = DATA_DIR / "hca_production.sqlite3"
INVOICE_FILE_DIR = DATA_DIR / "hca_invoice_files"
LEXWARE_SETTINGS_FILE = DATA_DIR / "hca_lexware_settings.json"
LEXWARE_BASE = "https://api.lexware.io"
MAIL_SETTINGS_FILE = DATA_DIR / "hca_mail_settings.json"
MAIL_ACCOUNTS_FILE = DATA_DIR / "hca_mail_accounts.json"
_PRODUCT_SEARCH_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_PRODUCT_SEARCH_CACHE_TTL = 300

MOBILE_PAIRINGS: dict[str, float] = {}
MOBILE_PAIRING_TTL_SECONDS = 300
HCA_BUSINESS_SCHEMA_VERSION = "0.13.5.1"

DOCUMENT_SETTINGS_KEY = "document_profile"
DOCUMENT_DEFAULTS = {
    "company_name": "Werbestudio Königswinter",
    "street": "Eulenbacherstraße 142",
    "postal_code": "53639",
    "city": "Königswinter",
    "country": "Deutschland",
    "phone": "02223 752 999 2",
    "email": "info@werbestudio-koenigswinter.de",
    "website": "www.werbestudio-koenigswinter.de",
    "vat_id": "DE293284680",
    "account_holder": "Werbestudio Königswinter",
    "bank_name": "",
    "iban": "",
    "bic": "",
}



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    INVOICE_FILE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS order_meta (
            order_id TEXT PRIMARY KEY,
            archived INTEGER NOT NULL DEFAULT 0,
            shipping_mode TEXT NOT NULL DEFAULT '',
            shipping_strategy TEXT NOT NULL DEFAULT 'manual_cheapest',
            parcel_json TEXT NOT NULL DEFAULT '{}',
            recipient_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shipments (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            shipment_key TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'standard',
            name TEXT NOT NULL DEFAULT '',
            recipient_json TEXT NOT NULL DEFAULT '{}',
            parcel_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            defer_reason TEXT NOT NULL DEFAULT '',
            error_text TEXT NOT NULL DEFAULT '',
            sendcloud_shipment_id TEXT NOT NULL DEFAULT '',
            sendcloud_parcel_id TEXT NOT NULL DEFAULT '',
            shipping_option_code TEXT NOT NULL DEFAULT '',
            contract_id TEXT NOT NULL DEFAULT '',
            carrier_name TEXT NOT NULL DEFAULT '',
            shipping_name TEXT NOT NULL DEFAULT '',
            price_value REAL,
            price_currency TEXT NOT NULL DEFAULT 'EUR',
            tracking_number TEXT NOT NULL DEFAULT '',
            tracking_url TEXT NOT NULL DEFAULT '',
            label_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(order_id, shipment_key)
        );
        CREATE INDEX IF NOT EXISTS idx_shipments_order ON shipments(order_id);
        CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
        CREATE TABLE IF NOT EXISTS shared_settings (
            setting_key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS thread_catalogs (
            catalog_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_filename TEXT NOT NULL DEFAULT '',
            color_count INTEGER NOT NULL DEFAULT 0,
            colors_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_thread_catalogs_name ON thread_catalogs(name);

        CREATE TABLE IF NOT EXISTS inventory_locations (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL DEFAULT '', is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory_articles (
            id TEXT PRIMARY KEY, woo_product_id TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', sku TEXT NOT NULL DEFAULT '', manufacturer TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '', raw_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_article_woo ON inventory_articles(woo_product_id) WHERE woo_product_id<>'';
        CREATE TABLE IF NOT EXISTS inventory_stock_items (
            id TEXT PRIMARY KEY, article_id TEXT NOT NULL, woo_product_id TEXT NOT NULL DEFAULT '', sku TEXT NOT NULL DEFAULT '', erp_code TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '', size TEXT NOT NULL DEFAULT '', barcode TEXT NOT NULL UNIQUE, physical_qty INTEGER NOT NULL DEFAULT 0, reserved_qty INTEGER NOT NULL DEFAULT 0, reorder_point INTEGER NOT NULL DEFAULT 0, location_id TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_stock_signature ON inventory_stock_items(woo_product_id,sku,erp_code,color,size);
        CREATE INDEX IF NOT EXISTS idx_inventory_barcode ON inventory_stock_items(barcode);
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, stock_item_id TEXT NOT NULL, movement_type TEXT NOT NULL, quantity INTEGER NOT NULL, reference_type TEXT NOT NULL DEFAULT '', reference_id TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_stock ON inventory_movements(stock_item_id,created_at);
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id TEXT PRIMARY KEY, order_id TEXT NOT NULL, item_id TEXT NOT NULL UNIQUE, stock_item_id TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, consumed_qty INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_reservations_stock ON inventory_reservations(stock_item_id,status);
        CREATE TABLE IF NOT EXISTS purchase_proposals (
            id TEXT PRIMARY KEY, stock_item_id TEXT NOT NULL UNIQUE, quantity INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open', supplier TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL DEFAULT '', api_type TEXT NOT NULL DEFAULT '', api_base_url TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchase_order_lines (
            id TEXT PRIMARY KEY, stock_item_id TEXT NOT NULL, proposal_id TEXT NOT NULL DEFAULT '', supplier TEXT NOT NULL DEFAULT '', order_reference TEXT NOT NULL DEFAULT '', ordered_qty INTEGER NOT NULL DEFAULT 0, received_qty INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ordered', note TEXT NOT NULL DEFAULT '', ordered_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_order_lines_stock ON purchase_order_lines(stock_item_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_purchase_order_lines_status ON purchase_order_lines(status,updated_at);
        CREATE TABLE IF NOT EXISTS mobile_devices (
            token_hash TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT 'Mobile-Device', user_agent TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory_warehouses (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL DEFAULT '', is_default INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_warehouse_code ON inventory_warehouses(code) WHERE code<>'';
        CREATE TABLE IF NOT EXISTS inventory_racks (
            id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL, name TEXT NOT NULL, code TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(warehouse_id,code)
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_racks_warehouse ON inventory_racks(warehouse_id,active,sort_order);
        CREATE TABLE IF NOT EXISTS inventory_bins (
            id TEXT PRIMARY KEY, warehouse_id TEXT NOT NULL, rack_id TEXT NOT NULL, name TEXT NOT NULL, code TEXT NOT NULL DEFAULT '', barcode TEXT NOT NULL UNIQUE, sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(rack_id,code)
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_bins_rack ON inventory_bins(rack_id,active,sort_order);
        CREATE INDEX IF NOT EXISTS idx_inventory_bins_barcode ON inventory_bins(barcode);
        CREATE TABLE IF NOT EXISTS inventory_bin_stock (
            bin_id TEXT NOT NULL, stock_item_id TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
            PRIMARY KEY(bin_id,stock_item_id)
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_bin_stock_item ON inventory_bin_stock(stock_item_id);
        """
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS business_sequences (
            doc_type TEXT PRIMARY KEY,
            year INTEGER NOT NULL,
            last_no INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crm_customers (
            id TEXT PRIMARY KEY,
            customer_no TEXT NOT NULL UNIQUE,
            customer_type TEXT NOT NULL DEFAULT 'customer',
            company_name TEXT NOT NULL DEFAULT '',
            salutation TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL DEFAULT '',
            website TEXT NOT NULL DEFAULT '',
            vat_id TEXT NOT NULL DEFAULT '',
            tax_no TEXT NOT NULL DEFAULT '',
            billing_street TEXT NOT NULL DEFAULT '',
            billing_zip TEXT NOT NULL DEFAULT '',
            billing_city TEXT NOT NULL DEFAULT '',
            billing_country TEXT NOT NULL DEFAULT 'DE',
            shipping_street TEXT NOT NULL DEFAULT '',
            shipping_zip TEXT NOT NULL DEFAULT '',
            shipping_city TEXT NOT NULL DEFAULT '',
            shipping_country TEXT NOT NULL DEFAULT 'DE',
            notes TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_crm_customers_name ON crm_customers(company_name,last_name,first_name);
        CREATE INDEX IF NOT EXISTS idx_crm_customers_email ON crm_customers(email);
        CREATE TABLE IF NOT EXISTS crm_contacts (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            salutation TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL DEFAULT '',
            is_primary INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_crm_contacts_customer ON crm_contacts(customer_id,active,last_name,first_name);
        CREATE TABLE IF NOT EXISTS crm_addresses (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            company_name TEXT NOT NULL DEFAULT '',
            attention TEXT NOT NULL DEFAULT '',
            street TEXT NOT NULL DEFAULT '',
            zip TEXT NOT NULL DEFAULT '',
            city TEXT NOT NULL DEFAULT '',
            country TEXT NOT NULL DEFAULT 'DE',
            is_default_billing INTEGER NOT NULL DEFAULT 0,
            is_default_shipping INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_crm_addresses_customer ON crm_addresses(customer_id,active,label);
        CREATE TABLE IF NOT EXISTS sales_quotes (
            id TEXT PRIMARY KEY,
            quote_no TEXT NOT NULL UNIQUE,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL DEFAULT '',
            contact_id TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            valid_until TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT 'EUR',
            intro_text TEXT NOT NULL DEFAULT '',
            footer_text TEXT NOT NULL DEFAULT '',
            internal_note TEXT NOT NULL DEFAULT '',
            sales_order_id TEXT NOT NULL DEFAULT '',
            sent_at TEXT NOT NULL DEFAULT '',
            accepted_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sales_quotes_customer ON sales_quotes(customer_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_sales_quotes_status ON sales_quotes(status,updated_at);
        CREATE TABLE IF NOT EXISTS sales_quote_items (
            id TEXT PRIMARY KEY,
            quote_id TEXT NOT NULL,
            position_no INTEGER NOT NULL DEFAULT 10,
            item_type TEXT NOT NULL DEFAULT 'product',
            product_id TEXT NOT NULL DEFAULT '',
            sku TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'Stk.',
            unit_price REAL NOT NULL DEFAULT 0,
            discount_pct REAL NOT NULL DEFAULT 0,
            tax_rate REAL NOT NULL DEFAULT 19,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sales_quote_items_quote ON sales_quote_items(quote_id,position_no);
        CREATE TABLE IF NOT EXISTS sales_orders (
            id TEXT PRIMARY KEY,
            order_no TEXT NOT NULL UNIQUE,
            source_quote_id TEXT NOT NULL DEFAULT '',
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL DEFAULT '',
            contact_id TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'confirmed',
            due_date TEXT NOT NULL DEFAULT '',
            customer_reference TEXT NOT NULL DEFAULT '',
            billing_json TEXT NOT NULL DEFAULT '{}',
            shipping_json TEXT NOT NULL DEFAULT '{}',
            internal_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sales_orders_customer ON sales_orders(customer_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_sales_orders_status ON sales_orders(status,updated_at);
        CREATE TABLE IF NOT EXISTS sales_order_items (
            id TEXT PRIMARY KEY,
            sales_order_id TEXT NOT NULL,
            position_no INTEGER NOT NULL DEFAULT 10,
            item_type TEXT NOT NULL DEFAULT 'product',
            product_id TEXT NOT NULL DEFAULT '',
            sku TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'Stk.',
            unit_price REAL NOT NULL DEFAULT 0,
            discount_pct REAL NOT NULL DEFAULT 0,
            tax_rate REAL NOT NULL DEFAULT 19,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sales_order_items_order ON sales_order_items(sales_order_id,position_no);
        CREATE TABLE IF NOT EXISTS production_order_links (
            id TEXT PRIMARY KEY,
            production_order_no TEXT NOT NULL UNIQUE,
            sales_order_id TEXT NOT NULL,
            base_order_id TEXT NOT NULL DEFAULT '',
            technique_group TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_production_order_links_sales ON production_order_links(sales_order_id,created_at);
        """
    )

    # Finanzen / Rechnungen / Lexware Office (v0.10.2)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS finance_invoices (
            id TEXT PRIMARY KEY,
            invoice_no TEXT NOT NULL UNIQUE,
            direction TEXT NOT NULL DEFAULT 'customer',
            source TEXT NOT NULL DEFAULT 'hca',
            sales_order_id TEXT NOT NULL DEFAULT '',
            customer_id TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            supplier_name TEXT NOT NULL DEFAULT '',
            external_invoice_no TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            payment_status TEXT NOT NULL DEFAULT '',
            invoice_date TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT 'EUR',
            billing_json TEXT NOT NULL DEFAULT '{}',
            shipping_json TEXT NOT NULL DEFAULT '{}',
            customer_reference TEXT NOT NULL DEFAULT '',
            purchase_reference TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            total_net REAL NOT NULL DEFAULT 0,
            total_tax REAL NOT NULL DEFAULT 0,
            total_gross REAL NOT NULL DEFAULT 0,
            tax_rate REAL NOT NULL DEFAULT 19,
            file_path TEXT NOT NULL DEFAULT '',
            file_name TEXT NOT NULL DEFAULT '',
            file_mime TEXT NOT NULL DEFAULT '',
            lexware_voucher_id TEXT NOT NULL DEFAULT '',
            lexware_voucher_type TEXT NOT NULL DEFAULT '',
            lexware_status TEXT NOT NULL DEFAULT '',
            lexware_open_amount REAL,
            lexware_deeplink TEXT NOT NULL DEFAULT '',
            lexware_synced_at TEXT NOT NULL DEFAULT '',
            finalized_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_finance_invoices_direction ON finance_invoices(direction,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_finance_invoices_order ON finance_invoices(sales_order_id,updated_at);
        CREATE INDEX IF NOT EXISTS idx_finance_invoices_customer ON finance_invoices(customer_id,updated_at);
        CREATE INDEX IF NOT EXISTS idx_finance_invoices_lexware ON finance_invoices(lexware_voucher_id);
        CREATE TABLE IF NOT EXISTS finance_invoice_items (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            position_no INTEGER NOT NULL DEFAULT 10,
            sku TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'Stk.',
            unit_price REAL NOT NULL DEFAULT 0,
            discount_pct REAL NOT NULL DEFAULT 0,
            tax_rate REAL NOT NULL DEFAULT 19,
            net_total REAL NOT NULL DEFAULT 0,
            tax_total REAL NOT NULL DEFAULT 0,
            gross_total REAL NOT NULL DEFAULT 0,
            source_item_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_finance_invoice_items_invoice ON finance_invoice_items(invoice_id,position_no);
        CREATE TABLE IF NOT EXISTS finance_lexware_vouchers (
            lexware_id TEXT PRIMARY KEY,
            voucher_type TEXT NOT NULL DEFAULT '',
            voucher_number TEXT NOT NULL DEFAULT '',
            contact_id TEXT NOT NULL DEFAULT '',
            contact_name TEXT NOT NULL DEFAULT '',
            total_amount REAL NOT NULL DEFAULT 0,
            open_amount REAL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            voucher_status TEXT NOT NULL DEFAULT '',
            voucher_date TEXT NOT NULL DEFAULT '',
            archived INTEGER NOT NULL DEFAULT 0,
            source_guess TEXT NOT NULL DEFAULT 'lexware',
            raw_json TEXT NOT NULL DEFAULT '{}',
            lexware_deeplink TEXT NOT NULL DEFAULT '',
            synced_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_finance_lexware_vouchers_type ON finance_lexware_vouchers(voucher_type,voucher_date);
        CREATE INDEX IF NOT EXISTS idx_finance_lexware_vouchers_number ON finance_lexware_vouchers(voucher_number);

        CREATE TABLE IF NOT EXISTS delivery_notes (
            id TEXT PRIMARY KEY,
            delivery_note_no TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL DEFAULT 'order',
            source_id TEXT NOT NULL DEFAULT '',
            sales_order_id TEXT NOT NULL DEFAULT '',
            invoice_id TEXT NOT NULL DEFAULT '',
            shipment_id TEXT NOT NULL DEFAULT '',
            customer_id TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            order_no TEXT NOT NULL DEFAULT '',
            invoice_no TEXT NOT NULL DEFAULT '',
            delivery_date TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            shipping_json TEXT NOT NULL DEFAULT '{}',
            recipient_email TEXT NOT NULL DEFAULT '',
            carrier_name TEXT NOT NULL DEFAULT '',
            tracking_number TEXT NOT NULL DEFAULT '',
            tracking_url TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            printed_at TEXT NOT NULL DEFAULT '',
            email_sent_at TEXT NOT NULL DEFAULT '',
            email_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_notes_order ON delivery_notes(sales_order_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_delivery_notes_invoice ON delivery_notes(invoice_id,created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_delivery_notes_shipment ON delivery_notes(shipment_id) WHERE shipment_id<>'';
        CREATE TABLE IF NOT EXISTS delivery_note_items (
            id TEXT PRIMARY KEY,
            delivery_note_id TEXT NOT NULL,
            position_no INTEGER NOT NULL DEFAULT 10,
            source_item_id TEXT NOT NULL DEFAULT '',
            variant_key TEXT NOT NULL DEFAULT '',
            sku TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            color TEXT NOT NULL DEFAULT '',
            size TEXT NOT NULL DEFAULT '',
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'Stk.',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_delivery_note_items_note ON delivery_note_items(delivery_note_id,position_no);
        CREATE INDEX IF NOT EXISTS idx_delivery_note_items_source ON delivery_note_items(source_item_id,variant_key);
        """
    )

    # CRM v0.10.1 migrations: default customer, multiple addresses and per-contact address defaults.
    customer_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(crm_customers)").fetchall()}
    if "is_default" not in customer_cols:
        conn.execute("ALTER TABLE crm_customers ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0")
    if "default_billing_address_id" not in customer_cols:
        conn.execute("ALTER TABLE crm_customers ADD COLUMN default_billing_address_id TEXT NOT NULL DEFAULT ''")
    if "default_shipping_address_id" not in customer_cols:
        conn.execute("ALTER TABLE crm_customers ADD COLUMN default_shipping_address_id TEXT NOT NULL DEFAULT ''")
    if "discount_pct" not in customer_cols:
        conn.execute("ALTER TABLE crm_customers ADD COLUMN discount_pct REAL NOT NULL DEFAULT 0")
    if "credit_balance" not in customer_cols:
        conn.execute("ALTER TABLE crm_customers ADD COLUMN credit_balance REAL NOT NULL DEFAULT 0")
    if "vouchers" not in customer_cols:
        conn.execute("ALTER TABLE crm_customers ADD COLUMN vouchers TEXT NOT NULL DEFAULT ''")
    finance_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(finance_invoices)").fetchall()}
    if "credit_note_id" not in finance_cols:
        conn.execute("ALTER TABLE finance_invoices ADD COLUMN credit_note_id TEXT NOT NULL DEFAULT ''")
    if "credit_note_no" not in finance_cols:
        conn.execute("ALTER TABLE finance_invoices ADD COLUMN credit_note_no TEXT NOT NULL DEFAULT ''")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS finance_credit_notes (
            id TEXT PRIMARY KEY,
            credit_note_no TEXT NOT NULL UNIQUE,
            invoice_id TEXT NOT NULL UNIQUE,
            customer_id TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            settlement_method TEXT NOT NULL DEFAULT 'offset',
            settlement_status TEXT NOT NULL DEFAULT '',
            total_net REAL NOT NULL DEFAULT 0,
            total_tax REAL NOT NULL DEFAULT 0,
            total_gross REAL NOT NULL DEFAULT 0,
            lexware_voucher_id TEXT NOT NULL DEFAULT '',
            lexware_status TEXT NOT NULL DEFAULT '',
            lexware_deeplink TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_finance_credit_notes_invoice ON finance_credit_notes(invoice_id);
    """)
    contact_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(crm_contacts)").fetchall()}
    if "default_billing_address_id" not in contact_cols:
        conn.execute("ALTER TABLE crm_contacts ADD COLUMN default_billing_address_id TEXT NOT NULL DEFAULT ''")
    if "default_shipping_address_id" not in contact_cols:
        conn.execute("ALTER TABLE crm_contacts ADD COLUMN default_shipping_address_id TEXT NOT NULL DEFAULT ''")
    quote_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(sales_quotes)").fetchall()}
    if "billing_address_id" not in quote_cols:
        conn.execute("ALTER TABLE sales_quotes ADD COLUMN billing_address_id TEXT NOT NULL DEFAULT ''")
    if "shipping_address_id" not in quote_cols:
        conn.execute("ALTER TABLE sales_quotes ADD COLUMN shipping_address_id TEXT NOT NULL DEFAULT ''")

    # HCA v0.12.0: document metadata, payment terms and editable templates.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payment_terms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            days INTEGER NOT NULL DEFAULT 14,
            text TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    if not conn.execute("SELECT 1 FROM payment_terms LIMIT 1").fetchone():
        now = _now()
        conn.execute("INSERT INTO payment_terms(id,name,days,text,is_default,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     ("payment-14-net", "14 Tage netto", 14, "Zahlbar innerhalb von 14 Tagen ohne Abzug.", 1, 1, now, now))
    for table, columns in {
        "crm_customers": [("payment_term_id", "TEXT NOT NULL DEFAULT ''"), ("woo_customer_id", "TEXT NOT NULL DEFAULT ''"), ("woo_synced_at", "TEXT NOT NULL DEFAULT ''")],
        "sales_quotes": [("source_channel", "TEXT NOT NULL DEFAULT ''"), ("payment_term_id", "TEXT NOT NULL DEFAULT ''"), ("payment_term_text", "TEXT NOT NULL DEFAULT ''"), ("duplicated_from_id", "TEXT NOT NULL DEFAULT ''")],
        "sales_orders": [("payment_term_id", "TEXT NOT NULL DEFAULT ''"), ("payment_term_text", "TEXT NOT NULL DEFAULT ''"), ("duplicated_from_id", "TEXT NOT NULL DEFAULT ''")],
        "finance_invoices": [("source_quote_id", "TEXT NOT NULL DEFAULT ''"), ("payment_term_id", "TEXT NOT NULL DEFAULT ''"), ("payment_term_text", "TEXT NOT NULL DEFAULT ''"), ("duplicated_from_id", "TEXT NOT NULL DEFAULT ''")],
        "delivery_notes": [("duplicated_from_id", "TEXT NOT NULL DEFAULT ''")],
    }.items():
        present = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, declaration in columns:
            if name not in present:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    # HCA v0.13.0: complete supplier records and explicit HCA/Woo product ownership.
    supplier_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(suppliers)").fetchall()}
    for name, declaration in [
        ("contact_name", "TEXT NOT NULL DEFAULT ''"), ("email", "TEXT NOT NULL DEFAULT ''"),
        ("phone", "TEXT NOT NULL DEFAULT ''"), ("website", "TEXT NOT NULL DEFAULT ''"),
        ("street", "TEXT NOT NULL DEFAULT ''"), ("zip", "TEXT NOT NULL DEFAULT ''"),
        ("city", "TEXT NOT NULL DEFAULT ''"), ("country", "TEXT NOT NULL DEFAULT 'DE'"),
        ("customer_no", "TEXT NOT NULL DEFAULT ''"), ("notes", "TEXT NOT NULL DEFAULT ''"),
    ]:
        if name not in supplier_cols:
            conn.execute(f"ALTER TABLE suppliers ADD COLUMN {name} {declaration}")
    article_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(inventory_articles)").fetchall()}
    for name, declaration in [
        ("description", "TEXT NOT NULL DEFAULT ''"), ("unit_price", "REAL NOT NULL DEFAULT 0"),
        ("tax_rate", "REAL NOT NULL DEFAULT 19"), ("source", "TEXT NOT NULL DEFAULT 'woocommerce'"),
        ("shop_status", "TEXT NOT NULL DEFAULT ''"),
    ]:
        if name not in article_cols:
            conn.execute(f"ALTER TABLE inventory_articles ADD COLUMN {name} {declaration}")

    # Existing single billing/shipping addresses are migrated once into the new address book.
    for customer in conn.execute("SELECT * FROM crm_customers").fetchall():
        existing = conn.execute("SELECT COUNT(*) FROM crm_addresses WHERE customer_id=?", (customer["id"],)).fetchone()[0]
        if existing:
            continue
        now = _now()
        bill = (str(customer["billing_street"] or "").strip(), str(customer["billing_zip"] or "").strip(), str(customer["billing_city"] or "").strip(), str(customer["billing_country"] or "DE").strip() or "DE")
        ship = (str(customer["shipping_street"] or "").strip(), str(customer["shipping_zip"] or "").strip(), str(customer["shipping_city"] or "").strip(), str(customer["shipping_country"] or customer["billing_country"] or "DE").strip() or "DE")
        company = _business_customer_name(customer) if "_business_customer_name" in globals() else str(customer["company_name"] or "")
        if any(bill[:3]):
            aid = str(uuid.uuid4())
            same = ship == bill or not any(ship[:3])
            conn.execute("INSERT INTO crm_addresses(id,customer_id,label,company_name,attention,street,zip,city,country,is_default_billing,is_default_shipping,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (aid,customer["id"],"Hauptadresse" if same else "Rechnungsadresse",company,"",bill[0],bill[1],bill[2],bill[3],1,1 if same else 0,1,now,now))
            conn.execute("UPDATE crm_customers SET default_billing_address_id=?, default_shipping_address_id=CASE WHEN ?=1 THEN ? ELSE default_shipping_address_id END WHERE id=?", (aid,1 if same else 0,aid,customer["id"]))
        if any(ship[:3]) and ship != bill:
            aid = str(uuid.uuid4())
            conn.execute("INSERT INTO crm_addresses(id,customer_id,label,company_name,attention,street,zip,city,country,is_default_billing,is_default_shipping,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (aid,customer["id"],"Lieferadresse",company,"",ship[0],ship[1],ship[2],ship[3],0,1,1,now,now))
            conn.execute("UPDATE crm_customers SET default_shipping_address_id=? WHERE id=?", (aid,customer["id"]))

    # Incremental inventory location migration. Existing stock remains unassigned until it is put away into a bin.
    movement_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(inventory_movements)").fetchall()}
    if "source_bin_id" not in movement_cols:
        conn.execute("ALTER TABLE inventory_movements ADD COLUMN source_bin_id TEXT NOT NULL DEFAULT ''")
    if "target_bin_id" not in movement_cols:
        conn.execute("ALTER TABLE inventory_movements ADD COLUMN target_bin_id TEXT NOT NULL DEFAULT ''")
    if "user_label" not in movement_cols:
        conn.execute("ALTER TABLE inventory_movements ADD COLUMN user_label TEXT NOT NULL DEFAULT ''")
    if not conn.execute("SELECT id FROM inventory_warehouses WHERE active=1 LIMIT 1").fetchone():
        now = _now()
        conn.execute("INSERT INTO inventory_warehouses(id,name,code,is_default,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", ("wh-main", "Hauptlager", "MAIN", 1, 1, now, now))

    row = conn.execute("SELECT id FROM inventory_locations WHERE is_default=1 LIMIT 1").fetchone()
    if not row:
        now = _now()
        conn.execute("INSERT INTO inventory_locations(id,name,code,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("main", "Hauptlager", "MAIN", 1, now, now))
    return conn


def _require_hca_key(request: Request, x_hca_key: str | None = Header(default=None), x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> None:
    expected = str(os.getenv("HCA_API_KEY", "") or "").strip()
    if expected and str(x_hca_key or "") != expected:
        raise HTTPException(status_code=401, detail="Ungültiger HCA API-Schlüssel.")
    session_required = globals().get("_hca135_requires_user_session")
    session_user = globals().get("_hca135_session_user")
    if callable(session_required) and callable(session_user) and session_required(str(request.url.path or "")):
        if not session_user(str(x_hca_session or "")):
            raise HTTPException(status_code=401, detail="HCA-Anmeldung erforderlich.")


auth = [Depends(_require_hca_key)]


def _internal_request(path: str, method: str = "GET", payload: Any = None, raw: bytes | None = None,
                      content_type: str = "application/json", timeout: int = 30) -> tuple[int, bytes, dict[str, str]]:
    url = INTERNAL_BASE + path
    headers = {"X-HCA-Key": str(os.getenv("HCA_API_KEY", "") or "")}
    data = raw
    if payload is not None:
        data = _json(payload).encode("utf-8")
        headers["Content-Type"] = content_type
    elif raw is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read(), dict(res.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, body, dict(exc.headers.items())


def _internal_json(path: str, method: str = "GET", payload: Any = None, timeout: int = 30) -> Any:
    status, body, _ = _internal_request(path, method, payload=payload, timeout=timeout)
    try:
        data = json.loads(body.decode("utf-8", "replace")) if body else {}
    except Exception:
        data = {"detail": body.decode("utf-8", "replace")}
    if not 200 <= status < 300:
        raise RuntimeError(data.get("error") or data.get("detail") or f"HCA Server HTTP {status}")
    return data


def _sendcloud_configured() -> bool:
    return bool(str(os.getenv("SENDCLOUD_PUBLIC_KEY", "")).strip() and str(os.getenv("SENDCLOUD_SECRET_KEY", "")).strip())


def _sendcloud_auth() -> str:
    public = str(os.getenv("SENDCLOUD_PUBLIC_KEY", "")).strip()
    secret = str(os.getenv("SENDCLOUD_SECRET_KEY", "")).strip()
    if not public or not secret:
        raise RuntimeError("Sendcloud ist nicht konfiguriert.")
    return "Basic " + base64.b64encode(f"{public}:{secret}".encode("utf-8")).decode("ascii")


def _sendcloud_error(status: int, body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8", "replace"))
        if isinstance(data, dict):
            errors = data.get("errors")
            if isinstance(errors, list) and errors:
                details = [str(x.get("detail") or x.get("message") or x) for x in errors if isinstance(x, dict)]
                if details:
                    return "; ".join(details)
            return str(data.get("detail") or data.get("message") or data.get("error") or data)
    except Exception:
        pass
    text = body.decode("utf-8", "replace").strip()
    return text or f"Sendcloud HTTP {status}"


def _sendcloud_request(path: str, method: str = "GET", payload: Any = None,
                       accept: str = "application/json", timeout: int = 45,
                       allow_status: tuple[int, ...] = (200, 201)) -> tuple[int, bytes, dict[str, str]]:
    url = SENDCLOUD_BASE + path
    headers = {"Authorization": _sendcloud_auth(), "Accept": accept}
    data = None
    if payload is not None:
        data = _json(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read()
            if res.status not in allow_status:
                raise RuntimeError(_sendcloud_error(res.status, body))
            return res.status, body, dict(res.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        if exc.code in allow_status:
            return exc.code, body, dict(exc.headers.items())
        raise RuntimeError(_sendcloud_error(exc.code, body)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Sendcloud nicht erreichbar: {exc.reason}") from exc


def _sendcloud_json(path: str, method: str = "GET", payload: Any = None,
                    timeout: int = 45, allow_status: tuple[int, ...] = (200, 201)) -> tuple[int, Any]:
    status, body, _ = _sendcloud_request(path, method, payload, timeout=timeout, allow_status=allow_status)
    try:
        return status, json.loads(body.decode("utf-8", "replace")) if body else {}
    except Exception as exc:
        raise RuntimeError("Sendcloud hat keine gültige JSON-Antwort geliefert.") from exc


def _sender_address(full: bool = True) -> dict[str, Any]:
    sender_id = str(os.getenv("SENDCLOUD_SENDER_ADDRESS_ID", "") or "").strip()
    if sender_id and not full:
        try:
            return {"sender_address_id": int(sender_id)}
        except Exception:
            return {"sender_address_id": sender_id}
    result = {
        "name": str(os.getenv("SENDCLOUD_FROM_NAME", "") or "").strip(),
        "company_name": str(os.getenv("SENDCLOUD_FROM_COMPANY", "") or "").strip(),
        "address_line_1": str(os.getenv("SENDCLOUD_FROM_ADDRESS1", "") or "").strip(),
        "house_number": str(os.getenv("SENDCLOUD_FROM_HOUSE_NUMBER", "") or "").strip(),
        "address_line_2": str(os.getenv("SENDCLOUD_FROM_ADDRESS2", "") or "").strip(),
        "postal_code": str(os.getenv("SENDCLOUD_FROM_POSTAL_CODE", "") or "").strip(),
        "city": str(os.getenv("SENDCLOUD_FROM_CITY", "") or "").strip(),
        "country_code": str(os.getenv("SENDCLOUD_FROM_COUNTRY", "DE") or "DE").strip().upper(),
        "phone_number": str(os.getenv("SENDCLOUD_FROM_PHONE", "") or "").strip(),
        "email": str(os.getenv("SENDCLOUD_FROM_EMAIL", "") or "").strip(),
    }
    return {k: v for k, v in result.items() if v not in (None, "")}


def _to_sendcloud_address(recipient: dict[str, Any]) -> dict[str, Any]:
    name = str(recipient.get("recipient_name") or recipient.get("name") or "").strip()
    company = str(recipient.get("company") or recipient.get("company_name") or "").strip()
    if not name:
        name = company
    result = {
        "name": name,
        "company_name": company,
        "address_line_1": str(recipient.get("address_line_1") or "").strip(),
        "house_number": str(recipient.get("house_number") or "").strip(),
        "address_line_2": str(recipient.get("address_line_2") or "").strip(),
        "postal_code": str(recipient.get("postal_code") or "").strip(),
        "city": str(recipient.get("city") or "").strip(),
        "country_code": str(recipient.get("country_code") or "DE").strip().upper(),
        "phone_number": str(recipient.get("phone") or recipient.get("phone_number") or "").strip(),
        "email": str(recipient.get("email") or "").strip(),
    }
    return {k: v for k, v in result.items() if v not in (None, "")}


def _validate_recipient(recipient: dict[str, Any]) -> None:
    a = _to_sendcloud_address(recipient)
    missing = []
    for key, label in [("name", "Empfänger"), ("address_line_1", "Straße"), ("postal_code", "PLZ"), ("city", "Ort"), ("country_code", "Land")]:
        if not str(a.get(key, "")).strip():
            missing.append(label)
    if missing:
        raise RuntimeError("Lieferadresse unvollständig: " + ", ".join(missing))


def _clean_parcel(parcel: dict[str, Any] | None) -> dict[str, float]:
    p = parcel or {}
    def num(name: str) -> float:
        try:
            return max(0.0, float(p.get(name) or 0))
        except Exception:
            return 0.0
    return {
        "weight_kg": round(num("weight_kg"), 3),
        "length_cm": round(num("length_cm"), 1),
        "width_cm": round(num("width_cm"), 1),
        "height_cm": round(num("height_cm"), 1),
    }


def _sendcloud_parcel(parcel: dict[str, Any]) -> dict[str, Any]:
    p = _clean_parcel(parcel)
    if p["weight_kg"] <= 0:
        raise RuntimeError("Paketgewicht fehlt.")
    result: dict[str, Any] = {"weight": {"value": f'{p["weight_kg"]:.3f}', "unit": "kg"}}
    if p["length_cm"] > 0 and p["width_cm"] > 0 and p["height_cm"] > 0:
        result["dimensions"] = {
            "length": f'{p["length_cm"]:.1f}', "width": f'{p["width_cm"]:.1f}', "height": f'{p["height_cm"]:.1f}', "unit": "cm"
        }
    return result


def _money(value: Any) -> tuple[float | None, str]:
    if isinstance(value, dict):
        cur = str(value.get("currency") or value.get("currency_code") or "EUR")
        for key in ("value", "amount"):
            try:
                if value.get(key) not in (None, ""):
                    return float(str(value.get(key)).replace(",", ".")), cur
            except Exception:
                pass
    try:
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return float(str(value).replace(",", ".")), "EUR"
    except Exception:
        pass
    return None, "EUR"


def _extract_quote_price(option: dict[str, Any]) -> tuple[float | None, str, str]:
    """Best effort over Sendcloud v3 quote shapes. Returns price, currency, contract id."""
    quotes = option.get("quotes")
    if not quotes:
        return None, "EUR", str(option.get("contract_id") or "")
    preferred_keys = ("total_price", "total", "price", "label_price", "shipping_price")
    found: list[tuple[int, float, str, str]] = []

    def walk(obj: Any, depth: int = 0, contract: str = "") -> None:
        if depth > 7:
            return
        if isinstance(obj, dict):
            contract_obj = obj.get("contract")
            contract_here = str(obj.get("contract_id") or (contract_obj.get("id") if isinstance(contract_obj, dict) else "") or contract or "")
            for rank, key in enumerate(preferred_keys):
                if key in obj:
                    val, cur = _money(obj.get(key))
                    if val is not None and val >= 0:
                        found.append((rank, val, cur, contract_here))
            # Common quote itself can be a money object.
            if "value" in obj and ("currency" in obj or "currency_code" in obj):
                val, cur = _money(obj)
                if val is not None and val >= 0:
                    found.append((5, val, cur, contract_here))
            for k, v in obj.items():
                if k not in preferred_keys:
                    walk(v, depth + 1, contract_here)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, depth + 1, contract)
    walk(quotes)
    if not found:
        return None, "EUR", str(option.get("contract_id") or "")
    found.sort(key=lambda x: (x[0], x[1]))
    _, value, currency, contract = found[0]
    return value, currency, contract or str(option.get("contract_id") or "")


def _normalize_option(option: dict[str, Any]) -> dict[str, Any]:
    price, currency, quote_contract = _extract_quote_price(option)
    contract = option.get("contract_id")
    if not contract and isinstance(option.get("contract"), dict):
        contract = option["contract"].get("id")
    contract = contract or quote_contract or ""
    carrier = option.get("carrier") if isinstance(option.get("carrier"), dict) else {}
    product = option.get("shipping_product") if isinstance(option.get("shipping_product"), dict) else {}
    return {
        "code": str(option.get("code") or option.get("shipping_option_code") or ""),
        "shipping_option_code": str(option.get("code") or option.get("shipping_option_code") or ""),
        "name": str(option.get("name") or product.get("name") or option.get("code") or "Versandart"),
        "carrier_name": str(carrier.get("name") or option.get("carrier_name") or option.get("carrier_code") or ""),
        "carrier_code": str(carrier.get("code") or option.get("carrier_code") or ""),
        "contract_id": contract,
        "price_value": price,
        "price_currency": currency,
        "quotes": option.get("quotes"),
    }


def _shipping_options(recipient: dict[str, Any], parcel: dict[str, Any]) -> list[dict[str, Any]]:
    _validate_recipient(recipient)
    payload = {
        "from_address": _sender_address(full=True),
        "to_address": _to_sendcloud_address(recipient),
        "parcels": [_sendcloud_parcel(parcel)],
        "calculate_quotes": True,
    }
    _, data = _sendcloud_json("/shipping-options", "POST", payload, timeout=45)
    options = data.get("data") if isinstance(data, dict) else []
    items = [_normalize_option(x) for x in (options or []) if isinstance(x, dict)]
    items.sort(key=lambda x: (x.get("price_value") is None, x.get("price_value") if x.get("price_value") is not None else 10**12, x.get("carrier_name", ""), x.get("name", "")))
    return items


def _fetch_label_png(parcel_id: str) -> bytes:
    if not parcel_id:
        raise RuntimeError("Sendcloud Parcel-ID fehlt; Versandlabel kann nicht geladen werden.")
    path = f"/parcels/{urllib.parse.quote(str(parcel_id))}/documents/label?dpi=300&paper_size=A6"
    _, body, _ = _sendcloud_request(path, "GET", accept="image/png", timeout=45, allow_status=(200,))
    if not body:
        raise RuntimeError("Sendcloud hat ein leeres Versandlabel geliefert.")
    return body


def _shipment_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["recipient"] = _loads(d.pop("recipient_json", "{}"), {})
    d["parcel"] = _loads(d.pop("parcel_json", "{}"), {})
    d["recipient_name"] = d["recipient"].get("recipient_name", "")
    d["company"] = d["recipient"].get("company", "")
    d["address_line_1"] = d["recipient"].get("address_line_1", "")
    d["house_number"] = d["recipient"].get("house_number", "")
    d["address_line_2"] = d["recipient"].get("address_line_2", "")
    d["postal_code"] = d["recipient"].get("postal_code", "")
    d["city"] = d["recipient"].get("city", "")
    d["country_code"] = d["recipient"].get("country_code", "DE")
    d["phone"] = d["recipient"].get("phone", "")
    d["email"] = d["recipient"].get("email", "")
    d["_shared"] = True
    return d


def _upsert_meta(order_id: str, values: dict[str, Any]) -> dict[str, Any]:
    order_id = str(order_id)
    now = _now()
    with _db() as conn:
        old = conn.execute("SELECT * FROM order_meta WHERE order_id=?", (order_id,)).fetchone()
        current = dict(old) if old else {}
        archived = 1 if bool(values.get("archived", current.get("archived", 0))) else 0
        mode = str(values.get("shipping_mode", current.get("shipping_mode", "")) or "")
        strategy = str(values.get("shipping_strategy", current.get("shipping_strategy", "manual_cheapest")) or "manual_cheapest")
        parcel = _clean_parcel(values.get("parcel") if "parcel" in values else _loads(current.get("parcel_json"), {}))
        recipient = values.get("recipient") if "recipient" in values else _loads(current.get("recipient_json"), {})
        recipient = recipient if isinstance(recipient, dict) else {}
        created = str(current.get("created_at") or now)
        conn.execute(
            """INSERT INTO order_meta(order_id,archived,shipping_mode,shipping_strategy,parcel_json,recipient_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(order_id) DO UPDATE SET archived=excluded.archived,shipping_mode=excluded.shipping_mode,
                 shipping_strategy=excluded.shipping_strategy,parcel_json=excluded.parcel_json,recipient_json=excluded.recipient_json,updated_at=excluded.updated_at""",
            (order_id, archived, mode, strategy, _json(parcel), _json(recipient), created, now),
        )
        if mode == "standard" and recipient:
            _validate_recipient(recipient)
            key = f"STD:{order_id}"
            sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"hca-standard:{order_id}"))
            existing = conn.execute("SELECT status FROM shipments WHERE order_id=? AND shipment_key=?", (order_id, key)).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO shipments(id,order_id,shipment_key,mode,name,recipient_json,parcel_json,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (sid, order_id, key, "standard", "Gesamtauftrag", _json(recipient), _json(parcel), "pending", now, now),
                )
            elif existing["status"] != "shipped":
                conn.execute("UPDATE shipments SET recipient_json=?,updated_at=? WHERE order_id=? AND shipment_key=?", (_json(recipient), now, order_id, key))
        elif mode in ("none", ""):
            conn.execute("DELETE FROM shipments WHERE order_id=? AND mode='standard' AND status!='shipped'", (order_id,))
        row = conn.execute("SELECT * FROM order_meta WHERE order_id=?", (order_id,)).fetchone()
    return _meta_row(row)


def _meta_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["archived"] = bool(d.get("archived"))
    d["parcel"] = _loads(d.pop("parcel_json", "{}"), {})
    d["recipient"] = _loads(d.pop("recipient_json", "{}"), {})
    return d


def _all_tasks() -> list[dict[str, Any]]:
    data = _internal_json("/api/tasks?workstation=all&open_only=0&limit=10000", timeout=30)
    return data.get("items", []) if isinstance(data, dict) and isinstance(data.get("items"), list) else []


def _refresh_statuses(tasks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    tasks = tasks if tasks is not None else _all_tasks()
    now = _now()
    with _db() as conn:
        rows = conn.execute("SELECT * FROM shipments WHERE status IN ('pending','ready','deferred','error')").fetchall()
        for row in rows:
            d = dict(row)
            oid = str(d["order_id"])
            mode = str(d["mode"])
            order_tasks = [t for t in tasks if str(t.get("order_id") or "") == oid]
            if mode == "merch":
                key = str(d["shipment_key"])
                relevant = [t for t in order_tasks if str(t.get("shipping_group") or "") == key]
            else:
                relevant = order_tasks
            if not relevant:
                continue
            complete = all((float(t.get("target_qty") or 0) > 0 and float(t.get("done_qty") or 0) >= float(t.get("target_qty") or 0)) for t in relevant)
            target = sum(float(t.get("target_qty") or 0) for t in relevant)
            done = sum(min(float(t.get("done_qty") or 0), float(t.get("target_qty") or 0)) for t in relevant)
            # Keep defer until user explicitly acts, but pending/error turns ready when production is complete.
            new_status = d["status"]
            if complete and d["status"] in ("pending", "error"):
                new_status = "ready"
            elif not complete and d["status"] == "ready":
                new_status = "pending"
            conn.execute("UPDATE shipments SET status=?,updated_at=? WHERE id=?", (new_status, now, d["id"]))
            # Computed quantities are returned dynamically, not stored.
        result = [_shipment_row(x) for x in conn.execute("SELECT * FROM shipments ORDER BY created_at DESC").fetchall()]
    task_map_order: dict[str, list[dict[str, Any]]] = {}
    for t in tasks:
        task_map_order.setdefault(str(t.get("order_id") or ""), []).append(t)
    for s in result:
        rel = task_map_order.get(str(s["order_id"]), [])
        if s["mode"] == "merch":
            rel = [t for t in rel if str(t.get("shipping_group") or "") == str(s["shipment_key"])]
        s["target_qty"] = int(sum(float(t.get("target_qty") or 0) for t in rel))
        s["done_qty"] = int(sum(min(float(t.get("done_qty") or 0), float(t.get("target_qty") or 0)) for t in rel))
        with _db() as conn:
            m = conn.execute("SELECT shipping_strategy FROM order_meta WHERE order_id=?", (str(s["order_id"]),)).fetchone()
        s["shipping_strategy"] = str(m["shipping_strategy"] if m else "manual_cheapest")
    for oid in {str(s["order_id"]) for s in result}:
        _sync_main_order_status(oid, tasks)
    return result


def _sync_main_order_status(order_id: str, tasks: list[dict[str, Any]] | None = None) -> None:
    """Keep the central HCA order status aligned with shared shipments.

    This is deliberately best-effort: a Sendcloud shipment that was already
    created must never be rolled back merely because the order-status endpoint
    is temporarily unavailable.
    """
    oid = str(order_id or "")
    if not oid:
        return
    try:
        with _db() as conn:
            rows = conn.execute("SELECT status FROM shipments WHERE order_id=?", (oid,)).fetchall()
        if not rows:
            return
        statuses = [str(r["status"] or "") for r in rows]
        if statuses and all(x == "shipped" for x in statuses):
            desired = "shipped"
        else:
            all_tasks = tasks if tasks is not None else _all_tasks()
            rel = [t for t in all_tasks if str(t.get("order_id") or "") == oid]
            complete = bool(rel) and all(
                float(t.get("target_qty") or 0) > 0
                and float(t.get("done_qty") or 0) >= float(t.get("target_qty") or 0)
                for t in rel
            )
            if not complete:
                return
            desired = "shipping_ready"
        _internal_json(f"/api/orders/{urllib.parse.quote(oid)}/status", "POST", {"status": desired}, 20)
    except Exception:
        pass


def _shipment_by_id(shipment_id: str) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM shipments WHERE id=?", (str(shipment_id),)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sendung nicht gefunden.")
    return _shipment_row(row)


def _save_parcel(shipment_id: str, parcel: dict[str, Any]) -> dict[str, float]:
    clean = _clean_parcel(parcel)
    if clean["weight_kg"] <= 0:
        raise RuntimeError("Bitte Paketgewicht eingeben.")
    with _db() as conn:
        conn.execute("UPDATE shipments SET parcel_json=?,updated_at=? WHERE id=?", (_json(clean), _now(), str(shipment_id)))
    return clean


def _ship(shipment_id: str, option: dict[str, Any], parcel: dict[str, Any] | None = None) -> dict[str, Any]:
    shipment = _shipment_by_id(shipment_id)
    if shipment["status"] == "shipped" and shipment.get("sendcloud_parcel_id"):
        return shipment
    if parcel is not None:
        shipment["parcel"] = _save_parcel(shipment_id, parcel)
    p = _clean_parcel(shipment.get("parcel"))
    if p["weight_kg"] <= 0:
        raise RuntimeError("Paketgewicht fehlt.")
    recipient = shipment["recipient"]
    _validate_recipient(recipient)
    code = str(option.get("shipping_option_code") or option.get("code") or "").strip()
    if not code:
        raise RuntimeError("shipping_option_code fehlt.")
    contract_id = option.get("contract_id")
    props: dict[str, Any] = {"shipping_option_code": code}
    if contract_id not in (None, ""):
        try:
            props["contract_id"] = int(contract_id)
        except Exception:
            props["contract_id"] = contract_id
    from_address = _sender_address(full=False)
    if not from_address:
        from_address = _sender_address(full=True)
    payload = {
        "label_details": {"mime_type": "image/png", "dpi": 300},
        "to_address": _to_sendcloud_address(recipient),
        "from_address": from_address,
        "ship_with": {"type": "shipping_option_code", "properties": props},
        "order_number": str(shipment.get("order_no") or shipment["order_id"]),
        "reference": f"HCA-{shipment["order_id"]}-{shipment["name"]}"[:120],
        "external_reference_id": f"hca-{shipment_id}",
        "parcels": [_sendcloud_parcel(p)],
    }
    with _db() as conn:
        conn.execute("UPDATE shipments SET status='shipping',error_text='',updated_at=? WHERE id=?", (_now(), shipment_id))
    try:
        status, data = _sendcloud_json("/shipments/announce", "POST", payload, timeout=60, allow_status=(201, 409))
        root = data.get("data", data) if isinstance(data, dict) else {}
        # On 409 Sendcloud can return the previously-created object. Accept it when parcel data is present.
        parcels = root.get("parcels", []) if isinstance(root, dict) else []
        if not parcels and status == 409:
            raise RuntimeError("Sendcloud meldet eine bereits vorhandene Sendung, liefert aber keine Parcel-Daten zurück. Bitte Sendcloud prüfen.")
        parcel_info = parcels[0] if parcels and isinstance(parcels[0], dict) else {}
        parcel_id = str(parcel_info.get("id") or "")
        label_bytes = _fetch_label_png(parcel_id)
        label_path = LABEL_DIR / f"{shipment_id}.png"
        label_path.write_bytes(label_bytes)
        price = option.get("price_value")
        try:
            price = float(price) if price not in (None, "") else None
        except Exception:
            price = None
        carrier = root.get("carrier") if isinstance(root.get("carrier"), dict) else {}
        now = _now()
        with _db() as conn:
            conn.execute(
                """UPDATE shipments SET status='shipped',sendcloud_shipment_id=?,sendcloud_parcel_id=?,shipping_option_code=?,contract_id=?,
                   carrier_name=?,shipping_name=?,price_value=?,price_currency=?,tracking_number=?,tracking_url=?,label_path=?,error_text='',updated_at=? WHERE id=?""",
                (
                    str(root.get("id") or ""), parcel_id, code, str(contract_id or ""),
                    str(carrier.get("name") or option.get("carrier_name") or option.get("carrier_code") or ""),
                    str(option.get("name") or code), price, str(option.get("price_currency") or "EUR"),
                    str(parcel_info.get("tracking_number") or ""), str(parcel_info.get("tracking_url") or ""),
                    str(label_path), now, shipment_id,
                ),
            )
        _sync_main_order_status(shipment["order_id"])
        return _shipment_by_id(shipment_id)
    except Exception as exc:
        with _db() as conn:
            conn.execute("UPDATE shipments SET status='ready',error_text=?,updated_at=? WHERE id=?", (str(exc), _now(), shipment_id))
        raise


def _norm_header(v: Any) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode("ascii").lower().strip()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


ALIASES = {
    "article": ["artikel", "artikelname", "product", "produkt"],
    "sku": ["art nr", "artikelnummer", "sku"],
    "size": ["größe", "grosse", "groesse", "size"],
    "team_name": ["ortsgruppe", "team", "team ortsgruppe", "abteilung"],
    "personalization_name": ["name personalisierung", "personalisierung", "aufdruck name", "name"],
    "number_text": ["nummer", "nr", "ruckennummer"],
    "techniques": ["verfahren", "veredelung", "veredelungsart", "technik"],
    "position": ["position", "druckposition", "stickposition"],
    "motif": ["motiv", "motivdatei", "datei"],
    "recipient_name": ["empfanger", "empfanger name", "versandname"],
    "first_name": ["empfanger vorname", "vorname"],
    "last_name": ["empfanger nachname", "nachname"],
    "company": ["empfanger firma", "firma", "unternehmen"],
    "address_line_1": ["strasse", "straße", "adresse", "address"],
    "house_number": ["hausnummer", "haus nr", "hnr"],
    "address_line_2": ["adresszusatz", "adresse 2", "address 2"],
    "postal_code": ["plz", "postleitzahl", "zip"],
    "city": ["ort", "stadt", "city"],
    "country_code": ["land", "landercode", "laendercode", "country"],
    "email": ["e mail", "email", "empfanger email"],
    "phone": ["telefon", "phone", "empfanger telefon"],
}
ALIASES = {k: {_norm_header(x) for x in vals} for k, vals in ALIASES.items()}


def _read_xlsx_stdlib(content: bytes) -> list[dict[str, Any]]:
    """Read the first XLSX worksheet using only Python's stdlib.

    The production container intentionally stays dependency-light; this keeps the
    merch import independent of openpyxl and therefore does not require changing
    the existing requirements.txt.
    """
    import zipfile
    import xml.etree.ElementTree as ET

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception as exc:
        raise RuntimeError("Die XLSX-Datei ist beschädigt oder kein gültiges Excel-Dokument.") from exc

    ns = {
        "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    }

    shared: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))

    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheet = workbook.find("m:sheets/m:sheet", ns)
    if sheet is None:
        return []
    rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    target = ""
    for rel in rels.findall("pr:Relationship", ns):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target", "")
            break
    if not target:
        raise RuntimeError("Erstes Tabellenblatt der XLSX-Datei konnte nicht gelesen werden.")
    if target.startswith("/"):
        sheet_path = target.lstrip("/")
    else:
        sheet_path = "xl/" + target.lstrip("/")
    sheet_path = str(Path(sheet_path)).replace("\\", "/")
    if sheet_path not in zf.namelist():
        # Normalize common '../worksheets/...' relation targets.
        import posixpath
        sheet_path = posixpath.normpath(posixpath.join("xl", target))
    root = ET.fromstring(zf.read(sheet_path))

    def col_index(ref: str) -> int:
        letters = re.match(r"([A-Za-z]+)", ref or "")
        if not letters:
            return 0
        n = 0
        for ch in letters.group(1).upper():
            n = n * 26 + (ord(ch) - 64)
        return max(0, n - 1)

    matrix: list[list[Any]] = []
    for row in root.findall(".//m:sheetData/m:row", ns):
        values: dict[int, Any] = {}
        max_col = -1
        for cell in row.findall("m:c", ns):
            idx = col_index(cell.attrib.get("r", ""))
            max_col = max(max_col, idx)
            typ = cell.attrib.get("t", "")
            val: Any = ""
            if typ == "inlineStr":
                inline = cell.find("m:is", ns)
                val = "".join(t.text or "" for t in inline.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")) if inline is not None else ""
            else:
                node = cell.find("m:v", ns)
                raw = node.text if node is not None and node.text is not None else ""
                if typ == "s":
                    try:
                        val = shared[int(raw)]
                    except Exception:
                        val = raw
                elif typ == "b":
                    val = raw == "1"
                else:
                    val = raw
            values[idx] = val
        if max_col >= 0:
            matrix.append([values.get(i, "") for i in range(max_col + 1)])
    if not matrix:
        return []
    headers = [str(x or "").strip() for x in matrix[0]]
    result: list[dict[str, Any]] = []
    for row in matrix[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        if any(str(x or "").strip() for x in padded):
            result.append(dict(zip(headers, padded[:len(headers)])))
    return result


def _read_table(content: bytes, filename: str) -> list[dict[str, Any]]:
    ext = Path(filename or "").suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        return _read_xlsx_stdlib(content)
    text = content.decode("utf-8-sig", "replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ";"
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def _pick(row: dict[str, Any], field: str) -> str:
    norm = {_norm_header(k): v for k, v in row.items()}
    for key in ALIASES[field]:
        if key in norm and norm[key] not in (None, ""):
            return str(norm[key]).strip()
    return ""


def _split_street_house(street: str, house: str) -> tuple[str, str]:
    street, house = street.strip(), house.strip()
    if house or not street:
        return street, house
    m = re.match(r"^(.*?)[,\s]+(\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)?)$", street)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return street, house


def _country_code(value: str) -> str:
    s = str(value or "").strip().upper()
    mapping = {"DEUTSCHLAND": "DE", "GERMANY": "DE", "ÖSTERREICH": "AT", "OESTERREICH": "AT", "AUSTRIA": "AT", "SCHWEIZ": "CH", "SWITZERLAND": "CH"}
    return mapping.get(s, s[:2] if len(s) >= 2 else "DE") or "DE"


def _decode_tch(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace")


def _parse_tch(content: bytes, source_filename: str = "") -> dict[str, Any]:
    if not content:
        raise ValueError("Die TCH-Datei ist leer.")
    text = _decode_tch(content)
    rows = csv.reader(io.StringIO(text))
    colors: list[dict[str, Any]] = []
    catalog_name = ""
    for row in rows:
        if len(row) < 7:
            continue
        code = str(row[0] or "").strip()
        catalog = str(row[1] or "").strip()
        color_name = str(row[2] or "").strip()
        thread_type = str(row[3] or "").strip()
        if not code or not catalog:
            continue
        try:
            rgb = [max(0, min(255, int(float(str(row[i]).strip())))) for i in (4, 5, 6)]
        except (TypeError, ValueError):
            continue
        if not catalog_name:
            catalog_name = catalog
        parts = catalog.split(None, 1)
        brand = parts[0] if parts else catalog
        series = parts[1] if len(parts) > 1 else catalog
        color_id = f"{brand}|{series}|{code}"
        colors.append({
            "id": color_id,
            "brand": brand,
            "series": series,
            "catalog": catalog,
            "code": code,
            "name": color_name,
            "type": thread_type,
            "rgb": rgb,
            "hex": "#%02x%02x%02x" % tuple(rgb),
        })
    if not colors:
        raise ValueError("In der TCH-Datei wurden keine gültigen Garnfarben gefunden.")
    if not catalog_name:
        catalog_name = Path(source_filename or "Garnkatalog").stem
    catalog_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "hca-thread-catalog:" + catalog_name.strip().lower()))
    return {
        "catalog_id": catalog_id,
        "name": catalog_name,
        "source_filename": str(source_filename or "").strip(),
        "color_count": len(colors),
        "colors": colors,
    }


def _thread_catalog_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "catalog_id": str(row["catalog_id"]),
        "name": str(row["name"] or ""),
        "source_filename": str(row["source_filename"] or ""),
        "color_count": int(row["color_count"] or 0),
        "colors": _loads(row["colors_json"], []),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


@router.get("/status", dependencies=auth)
async def shared_status() -> dict[str, Any]:
    with _db() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    return {"ok": True, "version": "1.6", "db": str(DB_PATH), "sendcloud_configured": _sendcloud_configured(), "schema": version, "thread_catalogs": True, "inventory": True, "inventory_schema": 2, "woocommerce_wsk_adapter": True, "business": True, "business_schema": HCA_BUSINESS_SCHEMA_VERSION}


@router.get("/orders/meta", dependencies=auth)
async def list_order_meta() -> dict[str, Any]:
    with _db() as conn:
        items = [_meta_row(r) for r in conn.execute("SELECT * FROM order_meta ORDER BY updated_at DESC").fetchall()]
    return {"ok": True, "items": items}


@router.get("/orders/{order_id}/meta", dependencies=auth)
async def get_order_meta(order_id: str) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM order_meta WHERE order_id=?", (str(order_id),)).fetchone()
    return {"ok": True, "item": _meta_row(row) if row else None}


@router.put("/orders/{order_id}/meta", dependencies=auth)
async def put_order_meta(order_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    try:
        item = _upsert_meta(order_id, body if isinstance(body, dict) else {})
        return {"ok": True, "item": item}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/orders/{order_id}/archive", dependencies=auth)
async def archive_order(order_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    item = _upsert_meta(order_id, {"archived": bool((body or {}).get("archived"))})
    return {"ok": True, "item": item}


@router.get("/settings/care-profiles", dependencies=auth)
async def get_care_profiles() -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT value_json,updated_at FROM shared_settings WHERE setting_key='care_profiles'").fetchone()
    return {"ok": True, "profiles": _loads(row["value_json"], None) if row else None, "updated_at": row["updated_at"] if row else None}


@router.put("/settings/care-profiles", dependencies=auth)
async def put_care_profiles(request: Request) -> dict[str, Any]:
    body = await request.json()
    profiles = body.get("profiles") if isinstance(body, dict) else None
    if not isinstance(profiles, dict):
        raise HTTPException(status_code=400, detail="Pflegeprofile fehlen.")
    # Keep payload bounded; SVG content is intentionally stored centrally as exact text.
    raw = _json(profiles)
    if len(raw.encode("utf-8")) > 4_000_000:
        raise HTTPException(status_code=413, detail="Pflegeprofile sind zu groß (maximal 4 MB zentral).")
    now = _now()
    with _db() as conn:
        conn.execute("INSERT INTO shared_settings(setting_key,value_json,updated_at) VALUES('care_profiles',?,?) ON CONFLICT(setting_key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at", (raw, now))
    return {"ok": True, "updated_at": now}


@router.get("/settings/thread-catalogs", dependencies=auth)
async def get_thread_catalogs() -> dict[str, Any]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM thread_catalogs ORDER BY name COLLATE NOCASE").fetchall()
    return {"ok": True, "items": [_thread_catalog_row(row) for row in rows]}


@router.post("/settings/thread-catalogs/import", dependencies=auth)
async def import_thread_catalog(request: Request, filename: str = "catalog.tch") -> dict[str, Any]:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Keine TCH-Datei übertragen.")
    if len(content) > 2_000_000:
        raise HTTPException(status_code=413, detail="TCH-Datei ist zu groß (maximal 2 MB).")
    try:
        parsed = _parse_tch(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = _now()
    with _db() as conn:
        existing = conn.execute("SELECT created_at FROM thread_catalogs WHERE catalog_id=?", (parsed["catalog_id"],)).fetchone()
        created_at = str(existing["created_at"]) if existing else now
        conn.execute(
            """INSERT INTO thread_catalogs(catalog_id,name,source_filename,color_count,colors_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(catalog_id) DO UPDATE SET
                 name=excluded.name,source_filename=excluded.source_filename,color_count=excluded.color_count,
                 colors_json=excluded.colors_json,updated_at=excluded.updated_at""",
            (parsed["catalog_id"], parsed["name"], parsed["source_filename"], parsed["color_count"], _json(parsed["colors"]), created_at, now),
        )
        row = conn.execute("SELECT * FROM thread_catalogs WHERE catalog_id=?", (parsed["catalog_id"],)).fetchone()
    return {"ok": True, "item": _thread_catalog_row(row), "updated": bool(existing)}


@router.delete("/settings/thread-catalogs/{catalog_id}", dependencies=auth)
async def delete_thread_catalog(catalog_id: str) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT name FROM thread_catalogs WHERE catalog_id=?", (str(catalog_id),)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Garnkatalog nicht gefunden.")
        conn.execute("DELETE FROM thread_catalogs WHERE catalog_id=?", (str(catalog_id),))
    return {"ok": True, "catalog_id": str(catalog_id), "name": str(row["name"] or "")}


@router.post("/merch-import", dependencies=auth)
async def merch_import(request: Request, filename: str = "merch.xlsx", order_no: str = "", customer: str = "", title: str = "", due_date: str = "",
                       weight_kg: float = 0, length_cm: float = 0, width_cm: float = 0, height_cm: float = 0,
                       shipping_strategy: str = "auto_cheapest") -> dict[str, Any]:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Keine Importdatei übertragen.")
    order_no = str(order_no or "").strip()
    if not order_no:
        raise HTTPException(status_code=400, detail="Auftragsnummer fehlt.")
    parcel = _clean_parcel({"weight_kg": weight_kg, "length_cm": length_cm, "width_cm": width_cm, "height_cm": height_cm})
    if parcel["weight_kg"] <= 0:
        raise HTTPException(status_code=400, detail="Für den Merchauftrag muss vor Produktionsbeginn das Versandgewicht eingetragen werden.")
    try:
        rows = _read_table(content, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not rows:
        raise HTTPException(status_code=400, detail="Die Tabelle enthält keine Datenzeilen.")
    items: list[dict[str, Any]] = []
    recipients: list[tuple[str, str, dict[str, Any]]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        article = _pick(row, "article")
        size = _pick(row, "size")
        first = _pick(row, "first_name")
        last = _pick(row, "last_name")
        recipient_name = _pick(row, "recipient_name") or " ".join(x for x in (first, last) if x).strip()
        street, house = _split_street_house(_pick(row, "address_line_1"), _pick(row, "house_number"))
        recipient = {
            "recipient_name": recipient_name,
            "company": _pick(row, "company"),
            "address_line_1": street,
            "house_number": house,
            "address_line_2": _pick(row, "address_line_2"),
            "postal_code": _pick(row, "postal_code"),
            "city": _pick(row, "city"),
            "country_code": _country_code(_pick(row, "country_code")),
            "email": _pick(row, "email"),
            "phone": _pick(row, "phone"),
        }
        if not article:
            errors.append(f"Zeile {index}: Artikel fehlt")
        if not size:
            errors.append(f"Zeile {index}: Größe fehlt")
        try:
            _validate_recipient(recipient)
        except Exception as exc:
            errors.append(f"Zeile {index}: {exc}")
        shipment_key = f"HCA-MERCH:{order_no}:{index-1:04d}"
        items.append({
            "article": article,
            "sku": _pick(row, "sku"),
            "size": size,
            "quantity": 1,
            "team_name": _pick(row, "team_name"),
            "personalization_name": _pick(row, "personalization_name"),
            "number_text": _pick(row, "number_text"),
            "techniques": _pick(row, "techniques") or "stick",
            "position": _pick(row, "position"),
            "motif": _pick(row, "motif"),
            "shipping_group": shipment_key,
        })
        recipients.append((shipment_key, recipient_name or f"Empfänger {index-1}", recipient))
    if errors:
        raise HTTPException(status_code=400, detail="Importprüfung fehlgeschlagen:\n" + "\n".join(errors[:30]))
    order_payload = {"order_no": order_no, "customer": str(customer or "").strip(), "title": str(title or "").strip() or "Merchauftrag / Einzelversand", "due_date": str(due_date or "").strip(), "items": items}
    try:
        created = await asyncio.to_thread(_internal_json, "/api/orders", "POST", order_payload, 45)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Produktionsauftrag konnte nicht angelegt werden: {exc}") from exc
    order_id = str(created.get("id") or created.get("order_id") or (created.get("item") or {}).get("id") or "") if isinstance(created, dict) else ""
    if not order_id:
        try:
            orders = await asyncio.to_thread(_internal_json, "/api/orders?limit=1000", "GET", None, 30)
            matches = [x for x in orders.get("items", []) if str(x.get("order_no") or "").strip() == order_no]
            if matches:
                order_id = str(matches[0].get("id") or "")
        except Exception:
            pass
    if not order_id:
        raise HTTPException(status_code=502, detail="Auftrag wurde angelegt, aber seine zentrale ID konnte nicht ermittelt werden.")
    _upsert_meta(order_id, {"shipping_mode": "merch", "shipping_strategy": shipping_strategy if shipping_strategy in ("auto_cheapest", "manual_cheapest") else "auto_cheapest", "parcel": parcel, "recipient": {}})
    now = _now()
    with _db() as conn:
        for shipment_key, name, recipient in recipients:
            sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"hca-merch:{order_id}:{shipment_key}"))
            conn.execute(
                """INSERT INTO shipments(id,order_id,shipment_key,mode,name,recipient_json,parcel_json,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(order_id,shipment_key) DO UPDATE SET name=excluded.name,recipient_json=excluded.recipient_json,parcel_json=excluded.parcel_json,updated_at=excluded.updated_at""",
                (sid, order_id, shipment_key, "merch", name, _json(recipient), _json(parcel), "pending", now, now),
            )
    return {"ok": True, "order_id": order_id, "order_no": order_no, "rows_imported": len(items), "shipments_created": len(recipients)}


@router.post("/refresh", dependencies=auth)
async def refresh_shipments() -> dict[str, Any]:
    try:
        tasks = await asyncio.to_thread(_all_tasks)
        items = await asyncio.to_thread(_refresh_statuses, tasks)
        return {"ok": True, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Produktionsstatus konnte nicht synchronisiert werden: {exc}") from exc


@router.get("/shipments", dependencies=auth)
async def list_shipments(status: str = "", order_id: str = "", limit: int = 5000, refresh: int = 1) -> dict[str, Any]:
    if refresh:
        try:
            tasks = await asyncio.to_thread(_all_tasks)
            await asyncio.to_thread(_refresh_statuses, tasks)
        except Exception:
            pass
    sql = "SELECT * FROM shipments WHERE 1=1"
    args: list[Any] = []
    if status:
        sql += " AND status=?"; args.append(status)
    if order_id:
        sql += " AND order_id=?"; args.append(str(order_id))
    sql += " ORDER BY created_at DESC LIMIT ?"; args.append(max(1, min(int(limit or 5000), 10000)))
    with _db() as conn:
        rows = [_shipment_row(r) for r in conn.execute(sql, args).fetchall()]
        metas = {str(r["order_id"]): _meta_row(r) for r in conn.execute("SELECT * FROM order_meta").fetchall()}
    # Add task quantities from one snapshot when possible.
    try:
        tasks = await asyncio.to_thread(_all_tasks)
    except Exception:
        tasks = []
    for s in rows:
        rel = [t for t in tasks if str(t.get("order_id") or "") == str(s["order_id"])]
        if s["mode"] == "merch":
            rel = [t for t in rel if str(t.get("shipping_group") or "") == str(s["shipment_key"])]
        s["target_qty"] = int(sum(float(t.get("target_qty") or 0) for t in rel))
        s["done_qty"] = int(sum(min(float(t.get("done_qty") or 0), float(t.get("target_qty") or 0)) for t in rel))
        meta = metas.get(str(s["order_id"]), {})
        s["shipping_strategy"] = meta.get("shipping_strategy", "manual_cheapest")
    # Enrich with order text using public central API, without coupling to its DB schema.
    try:
        orders = await asyncio.to_thread(_internal_json, "/api/orders?limit=1000", "GET", None, 30)
        omap = {str(x.get("id") or ""): x for x in orders.get("items", [])}
        for s in rows:
            o = omap.get(str(s["order_id"]), {})
            s["order_no"] = o.get("order_no") or ""
            s["customer"] = o.get("customer") or ""
            s["title"] = o.get("title") or ""
    except Exception:
        pass
    return {"ok": True, "items": rows}


@router.post("/shipments/{shipment_id}/shipping-options", dependencies=auth)
async def shipment_options(shipment_id: str, request: Request) -> dict[str, Any]:
    shipment = _shipment_by_id(shipment_id)
    body = await request.json()
    parcel = _clean_parcel(body if isinstance(body, dict) else shipment.get("parcel"))
    if parcel["weight_kg"] <= 0:
        parcel = _clean_parcel(shipment.get("parcel"))
    try:
        parcel = _save_parcel(shipment_id, parcel)
        items = await asyncio.to_thread(_shipping_options, shipment["recipient"], parcel)
        return {"ok": True, "items": items, "cheapest": items[0] if items and items[0].get("price_value") is not None else None}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/shipments/{shipment_id}/ship", dependencies=auth)
async def ship_shipment(shipment_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    body = body if isinstance(body, dict) else {}
    option = {
        "shipping_option_code": body.get("shipping_option_code") or body.get("code"),
        "contract_id": body.get("contract_id"),
        "name": body.get("shipping_name") or body.get("name") or "",
        "carrier_name": body.get("carrier_name") or "",
        "price_value": body.get("price_value"),
        "price_currency": body.get("price_currency") or "EUR",
    }
    try:
        shipment = await asyncio.to_thread(_ship, shipment_id, option, body)
        note = await asyncio.to_thread(_delivery_from_shipment_blocking, shipment_id)
        email = await _delivery_try_auto_email(str(note["id"])) if not note.get("email_sent_at") else {"ok": True, "already_sent": True}
        return {"ok": True, "item": shipment, "tracking_number": shipment.get("tracking_number", ""), "label_url": f"/api/hca-shared/shipments/{shipment_id}/label", "delivery_note": note, "delivery_note_email": email}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/shipments/{shipment_id}/auto-ship", dependencies=auth)
async def auto_ship(shipment_id: str) -> dict[str, Any]:
    shipment = _shipment_by_id(shipment_id)
    if shipment["status"] == "shipped":
        note = await asyncio.to_thread(_delivery_from_shipment_blocking, shipment_id)
        email = await _delivery_try_auto_email(str(note["id"])) if not note.get("email_sent_at") else {"ok": True, "already_sent": True}
        return {"ok": True, "item": shipment, "already_shipped": True, "label_url": f"/api/hca-shared/shipments/{shipment_id}/label", "delivery_note": note, "delivery_note_email": email}
    if shipment["status"] != "ready":
        raise HTTPException(status_code=409, detail="Diese Einzelsendung ist noch nicht versandbereit.")
    try:
        items = await asyncio.to_thread(_shipping_options, shipment["recipient"], shipment["parcel"])
        priced = [x for x in items if x.get("price_value") is not None and x.get("shipping_option_code")]
        if not priced:
            raise RuntimeError("Sendcloud liefert keine Versandart mit berechenbarem Preis. Die Sendung bleibt versandbereit und muss manuell geprüft werden.")
        cheapest = priced[0]
        shipped = await asyncio.to_thread(_ship, shipment_id, cheapest, None)
        note = await asyncio.to_thread(_delivery_from_shipment_blocking, shipment_id)
        email = await _delivery_try_auto_email(str(note["id"])) if not note.get("email_sent_at") else {"ok": True, "already_sent": True}
        return {"ok": True, "item": shipped, "selected_option": cheapest, "tracking_number": shipped.get("tracking_number", ""), "label_url": f"/api/hca-shared/shipments/{shipment_id}/label", "delivery_note": note, "delivery_note_email": email}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/task-finished", dependencies=auth)
async def task_finished(request: Request) -> dict[str, Any]:
    body = await request.json()
    order_id = str((body or {}).get("order_id") or "")
    shipment_key = str((body or {}).get("shipment_key") or "")
    if not order_id or not shipment_key:
        return {"ok": True, "shipment": None, "action": "none"}
    try:
        tasks = await asyncio.to_thread(_all_tasks)
        await asyncio.to_thread(_refresh_statuses, tasks)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Produktionsstatus konnte nicht geprüft werden: {exc}") from exc
    with _db() as conn:
        row = conn.execute("SELECT * FROM shipments WHERE order_id=? AND shipment_key=? AND mode='merch'", (order_id, shipment_key)).fetchone()
        meta = conn.execute("SELECT shipping_strategy FROM order_meta WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return {"ok": True, "shipment": None, "action": "none"}
    shipment = _shipment_row(row)
    strategy = str(meta["shipping_strategy"] if meta else "manual_cheapest")
    if shipment["status"] != "ready":
        return {"ok": True, "shipment": shipment, "action": "none"}
    if strategy != "auto_cheapest" or not bool((body or {}).get("auto_ship", True)):
        return {"ok": True, "shipment": shipment, "action": "ready"}
    try:
        items = await asyncio.to_thread(_shipping_options, shipment["recipient"], shipment["parcel"])
        priced = [x for x in items if x.get("price_value") is not None and x.get("shipping_option_code")]
        if not priced:
            raise RuntimeError("Keine Sendcloud-Versandart mit berechenbarem Preis verfügbar.")
        cheapest = priced[0]
        shipped = await asyncio.to_thread(_ship, shipment["id"], cheapest, None)
        note = await asyncio.to_thread(_delivery_from_shipment_blocking, shipment["id"])
        email = await _delivery_try_auto_email(str(note["id"])) if not note.get("email_sent_at") else {"ok": True, "already_sent": True}
        return {"ok": True, "shipment": shipped, "action": "shipped", "selected_option": cheapest, "tracking_number": shipped.get("tracking_number", ""), "label_url": f"/api/hca-shared/shipments/{shipment["id"]}/label", "delivery_note": note, "delivery_note_email": email}
    except Exception as exc:
        return {"ok": False, "shipment": _shipment_by_id(shipment["id"]), "action": "error", "error": str(exc)}


@router.get("/shipments/{shipment_id}/label", dependencies=auth)
async def shipment_label(shipment_id: str):
    shipment = _shipment_by_id(shipment_id)
    path = Path(str(shipment.get("label_path") or ""))
    if path.is_file():
        return FileResponse(path, media_type="image/png", filename=f"HCA_Versandlabel_{shipment_id}.png")
    parcel_id = str(shipment.get("sendcloud_parcel_id") or "")
    if not parcel_id:
        raise HTTPException(status_code=404, detail="Für diese Sendung wurde noch kein Versandlabel erstellt.")
    try:
        label = await asyncio.to_thread(_fetch_label_png, parcel_id)
        LABEL_DIR.mkdir(parents=True, exist_ok=True)
        path = LABEL_DIR / f"{shipment_id}.png"
        path.write_bytes(label)
        with _db() as conn:
            conn.execute("UPDATE shipments SET label_path=?,updated_at=? WHERE id=?", (str(path), _now(), shipment_id))
        return Response(content=label, media_type="image/png", headers={"Content-Disposition": f'inline; filename="HCA_Versandlabel_{shipment_id}.png"'})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/shipments/{shipment_id}/defer", dependencies=auth)
async def defer_shipment(shipment_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    reason = str((body or {}).get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Bitte einen Grund für die Zurückstellung angeben.")
    with _db() as conn:
        row = conn.execute("SELECT status FROM shipments WHERE id=?", (shipment_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sendung nicht gefunden.")
        if row["status"] == "shipped":
            raise HTTPException(status_code=409, detail="Eine bereits versendete Sendung kann nicht zurückgestellt werden.")
        conn.execute("UPDATE shipments SET status='deferred',defer_reason=?,updated_at=? WHERE id=?", (reason, _now(), shipment_id))
    return {"ok": True, "item": _shipment_by_id(shipment_id)}


# --- Artikelstamm / Lager / Beschaffung (v0.9.22) ---
def _base_db() -> sqlite3.Connection:
    conn = sqlite3.connect(BASE_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def _meta_dict(obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in obj.get("meta_data") or []:
        if isinstance(row, dict) and str(row.get("key") or ""):
            out[str(row.get("key"))] = row.get("value")
    return out


def _as_data(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _slug_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _product_manufacturer(meta: dict[str, Any], product: dict[str, Any]) -> str:
    for key in ("_wst_fr_manufacturer_name", "_wk_printprodukt_manufacturer", "_manufacturer", "manufacturer", "_product_manufacturer"):
        if str(meta.get(key) or "").strip():
            return str(meta.get(key)).strip()
    for attr in product.get("attributes") or []:
        if isinstance(attr, dict) and _slug_text(attr.get("name")) in {"hersteller", "manufacturer", "marke", "brand"}:
            opts = attr.get("options") or []
            if opts:
                return str(opts[0]).strip()
    return ""


def _product_supplier(meta: dict[str, Any]) -> str:
    # The Falk & Ross source columns may contain a brand/manufacturer name.
    # The commercial supplier is nevertheless always Falk & Ross.
    if str(meta.get("_wst_fr_supplier") or meta.get("_wst_fr_supplier_code") or "").strip():
        return "Falk & Ross"
    # Axpol items carry ERP codes per color. Keep supplier explicit for purchasing suggestions.
    colors = _as_data(meta.get("werbeartikel_colors"), [])
    if isinstance(colors, list) and any(isinstance(c, dict) and str(c.get("CodeERP") or "").strip() for c in colors):
        return "Axpol"
    return ""


def _wsk_product_configs(product: dict[str, Any]) -> list[dict[str, Any]]:
    meta = _meta_dict(product)
    colors = _as_data(meta.get("werbeartikel_colors"), [])
    sizes = _as_data(meta.get("_wst_sizes_enabled"), [])
    custom_sizes = _as_data(meta.get("_wst_custom_sizes"), [])
    size_runs = _as_data(meta.get("_wst_size_runs"), [])
    if not isinstance(colors, list): colors = []
    if not isinstance(sizes, list): sizes = []
    if isinstance(custom_sizes, list):
        for size in custom_sizes:
            if str(size).strip() and str(size).strip() not in sizes: sizes.append(str(size).strip())
    sizes = [str(x).strip() for x in sizes if str(x).strip()]
    run_by_color: dict[str, list[str]] = {}
    if isinstance(size_runs, list):
        for run in size_runs:
            if not isinstance(run, dict): continue
            rs = [str(x).strip() for x in (run.get("sizes") or []) if str(x).strip()]
            for c in run.get("colors") or []:
                run_by_color[_slug_text(c)] = rs
    product_id = int(product.get("id") or 0)
    name = str(product.get("name") or "").strip(); sku = str(product.get("sku") or "").strip()
    images = product.get("images") or []; image = str(images[0].get("src") or "") if images and isinstance(images[0], dict) else ""
    manufacturer = _product_manufacturer(meta, product); supplier = _product_supplier(meta)
    common = {"product_id": product_id, "name": name, "sku": sku, "image": image, "weight": str(product.get("weight") or ""), "dimensions": product.get("dimensions") if isinstance(product.get("dimensions"), dict) else {}, "stock_status": str(product.get("stock_status") or ""), "manufacturer": manufacturer, "supplier": supplier, "wsk": True, "price": product.get("price"), "regular_price": product.get("regular_price"), "areas": _as_data(meta.get("werbeartikel_areas"), []) if isinstance(_as_data(meta.get("werbeartikel_areas"), []), list) else []}
    result: list[dict[str, Any]] = []
    if colors:
        for i, row in enumerate(colors):
            if not isinstance(row, dict): continue
            color = str(row.get("name") or row.get("color") or "").strip()
            erp = str(row.get("CodeERP") or row.get("codeerp") or row.get("fr_color_code") or "").strip()
            c_sizes = run_by_color.get(_slug_text(color), sizes)
            result.append({**common, "key": f"{product_id}:wsk:{i}", "color": color, "erp_code": erp, "sizes": c_sizes, "size_skus": {}, "matched_sku": sku})
    elif sizes:
        result.append({**common, "key": f"{product_id}:wsk", "color": "", "erp_code": "", "sizes": sizes, "size_skus": {}, "matched_sku": sku})
    return result


def _stock_signature(woo_product_id: Any, sku: Any, erp_code: Any, color: Any, size: Any) -> str:
    return "|".join(str(x or "").strip().lower() for x in (woo_product_id, sku, erp_code, color, size))


def _stock_id(woo_product_id: Any, sku: Any, erp_code: Any, color: Any, size: Any) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "hca-stock:" + _stock_signature(woo_product_id, sku, erp_code, color, size)))


def _barcode_for(stock_id: str) -> str:
    return "HCA-S-" + str(stock_id).replace("-", "")[:16].upper()


def _ensure_inventory_article(conn: sqlite3.Connection, *, woo_product_id: str, name: str, sku: str, manufacturer: str = "", supplier: str = "", image_url: str = "", raw: Any = None, preserve_existing_raw: bool = False) -> str:
    now = _now(); existing = conn.execute("SELECT id,raw_json FROM inventory_articles WHERE woo_product_id=?", (str(woo_product_id),)).fetchone() if woo_product_id else None
    article_id = str(existing["id"]) if existing else str(uuid.uuid5(uuid.NAMESPACE_URL, f"hca-article:{woo_product_id or sku or name}"))
    raw_json = str(existing["raw_json"] or "{}") if preserve_existing_raw and existing else _json(raw or {})
    conn.execute("""INSERT INTO inventory_articles(id,woo_product_id,name,sku,manufacturer,supplier,image_url,raw_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE inventory_articles.name END,
                    sku=CASE WHEN excluded.sku<>'' THEN excluded.sku ELSE inventory_articles.sku END,
                    manufacturer=CASE WHEN excluded.manufacturer<>'' THEN excluded.manufacturer ELSE inventory_articles.manufacturer END,
                    supplier=CASE WHEN excluded.supplier<>'' THEN excluded.supplier ELSE inventory_articles.supplier END,
                    image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE inventory_articles.image_url END,
                    raw_json=excluded.raw_json,updated_at=excluded.updated_at""",
                 (article_id,str(woo_product_id),str(name),str(sku),str(manufacturer),str(supplier),str(image_url),raw_json,now,now))
    return article_id


def _ensure_stock_item(conn: sqlite3.Connection, *, article_id: str, woo_product_id: str, sku: str, erp_code: str, color: str, size: str) -> str:
    sid = _stock_id(woo_product_id, sku, erp_code, color, size); now = _now()
    conn.execute("""INSERT INTO inventory_stock_items(id,article_id,woo_product_id,sku,erp_code,color,size,barcode,location_id,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET article_id=excluded.article_id,sku=excluded.sku,erp_code=excluded.erp_code,color=excluded.color,size=excluded.size,active=1,updated_at=excluded.updated_at""",
                 (sid,article_id,str(woo_product_id),str(sku),str(erp_code),str(color),str(size),_barcode_for(sid),"main",now,now))
    return sid


def _refresh_stock_totals(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id FROM inventory_stock_items").fetchall()
    for r in rows:
        sid = str(r["id"])
        reserved = conn.execute("SELECT COALESCE(SUM(MAX(quantity-consumed_qty,0)),0) q FROM inventory_reservations WHERE stock_item_id=? AND status='active'", (sid,)).fetchone()["q"]
        conn.execute("UPDATE inventory_stock_items SET reserved_qty=?,updated_at=? WHERE id=?", (int(reserved or 0),_now(),sid))
        stock = conn.execute("SELECT physical_qty,reserved_qty,reorder_point FROM inventory_stock_items WHERE id=?", (sid,)).fetchone()
        on_order_row = conn.execute("SELECT COALESCE(SUM(CASE WHEN ordered_qty>received_qty THEN ordered_qty-received_qty ELSE 0 END),0) q FROM purchase_order_lines WHERE stock_item_id=? AND status IN ('ordered','partial')", (sid,)).fetchone()
        on_order = int(on_order_row["q"] or 0) if on_order_row else 0
        shortage = max(0, int(stock["reserved_qty"] or 0) + int(stock["reorder_point"] or 0) - int(stock["physical_qty"] or 0) - on_order)
        proposal = conn.execute("SELECT id,status FROM purchase_proposals WHERE stock_item_id=?", (sid,)).fetchone()
        if shortage > 0:
            pid = str(proposal["id"]) if proposal else str(uuid.uuid4())
            conn.execute("""INSERT INTO purchase_proposals(id,stock_item_id,quantity,status,created_at,updated_at) VALUES(?,?,?,?,?,?)
                            ON CONFLICT(stock_item_id) DO UPDATE SET quantity=excluded.quantity,status='open',updated_at=excluded.updated_at""", (pid,sid,shortage,"open",_now(),_now()))
        elif proposal and str(proposal["status"]) in {"open","covered"}:
            conn.execute("UPDATE purchase_proposals SET quantity=0,status='covered',updated_at=? WHERE stock_item_id=?", (_now(),sid))


def _reconcile_inventory_from_orders() -> dict[str, int]:
    if not BASE_DB_PATH.exists():
        return {"articles":0,"stock_items":0,"reservations":0}
    with _base_db() as base:
        rows = base.execute("""SELECT i.*,o.source_type,o.status order_status,o.order_no
                               FROM items i JOIN orders o ON o.id=i.order_id
                               WHERE o.source_type='woocommerce' AND o.status<>'shipped'""").fetchall()
        current_item_ids = {str(r["id"]) for r in rows}
    articles=set(); stocks=set(); reservations=0
    with _db() as conn:
        existing = conn.execute("SELECT item_id FROM inventory_reservations WHERE status='active'").fetchall()
        for rr in existing:
            if str(rr["item_id"]) not in current_item_ids:
                conn.execute("UPDATE inventory_reservations SET status='cancelled',updated_at=? WHERE item_id=?", (_now(),str(rr["item_id"])))
        for r in rows:
            raw = _loads(r["raw_json"], {}) if "raw_json" in r.keys() else {}
            supplier = str(raw.get("supplier") or "") if isinstance(raw,dict) else ""
            article_id = _ensure_inventory_article(conn, woo_product_id=str(r["product_id"] or ""), name=str(r["article"] or ""), sku=str(r["sku"] or ""), manufacturer=str(r["manufacturer"] or ""), supplier=supplier, image_url=str(r["image_url"] or ""), raw=raw, preserve_existing_raw=True)
            sid = _ensure_stock_item(conn, article_id=article_id, woo_product_id=str(r["product_id"] or ""), sku=str(r["sku"] or ""), erp_code=str(r["erp_code"] or "") if "erp_code" in r.keys() else "", color=str(r["color"] or ""), size=str(r["size"] or ""))
            articles.add(article_id); stocks.add(sid); qty=max(1,int(r["quantity"] or 1)); now=_now()
            ex=conn.execute("SELECT id,consumed_qty FROM inventory_reservations WHERE item_id=?", (str(r["id"]),)).fetchone()
            rid=str(ex["id"]) if ex else str(uuid.uuid4()); consumed=min(qty,int(ex["consumed_qty"] or 0)) if ex else 0
            conn.execute("""INSERT INTO inventory_reservations(id,order_id,item_id,stock_item_id,quantity,consumed_qty,status,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET stock_item_id=excluded.stock_item_id,quantity=excluded.quantity,consumed_qty=?,status='active',updated_at=excluded.updated_at""",
                         (rid,str(r["order_id"]),str(r["id"]),sid,qty,consumed,"active",now,now,consumed))
            reservations += 1
        _refresh_stock_totals(conn)
    return {"articles":len(articles),"stock_items":len(stocks),"reservations":reservations}


def _stock_item_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    d=dict(row); d["available_qty"]=int(d.get("physical_qty") or 0)-int(d.get("reserved_qty") or 0)
    try:
        d["allocated_qty"]=_allocated_qty(conn,str(d.get("id") or ""))
    except Exception:
        d["allocated_qty"]=0
    d["unassigned_qty"]=max(0,int(d.get("physical_qty") or 0)-int(d.get("allocated_qty") or 0))
    art=conn.execute("SELECT name,sku,woo_product_id,manufacturer,supplier,image_url FROM inventory_articles WHERE id=?", (d.get("article_id"),)).fetchone()
    if art:
        d.update({
            "article":art["name"],
            "article_sku":art["sku"],
            "article_woo_product_id":art["woo_product_id"],
            "manufacturer":art["manufacturer"],
            "supplier":art["supplier"],
            "image_url":art["image_url"],
        })
    proposal=conn.execute("SELECT id,quantity,status FROM purchase_proposals WHERE stock_item_id=?", (d["id"],)).fetchone()
    d["proposal_id"]=str(proposal["id"]) if proposal else ""
    d["proposal_qty"]=int(proposal["quantity"] or 0) if proposal and str(proposal["status"]) in {"open","covered"} else 0
    d["proposal_status"]=str(proposal["status"]) if proposal else ""
    oo=conn.execute("SELECT COALESCE(SUM(CASE WHEN ordered_qty>received_qty THEN ordered_qty-received_qty ELSE 0 END),0) q FROM purchase_order_lines WHERE stock_item_id=? AND status IN ('ordered','partial')", (d["id"],)).fetchone()
    d["on_order_qty"]=int(oo["q"] or 0) if oo else 0
    return d


def _inventory_article_detail(conn: sqlite3.Connection, article_id: str) -> dict[str, Any]:
    row=conn.execute("SELECT * FROM inventory_articles WHERE id=?", (str(article_id),)).fetchone()
    if not row:
        raise HTTPException(status_code=404,detail="Artikel nicht gefunden.")
    article=dict(row)
    raw=_loads(article.get("raw_json"), {})
    if not isinstance(raw,dict): raw={}
    variants=[_stock_item_row(conn,r) for r in conn.execute("SELECT * FROM inventory_stock_items WHERE article_id=? AND active=1 ORDER BY color,size,sku", (str(article_id),)).fetchall()]
    for variant in variants:
        try:
            variant["bins"]=_bin_stock_rows(conn,str(variant.get("id") or ""))
        except Exception:
            variant["bins"]=[]
    article.pop("raw_json",None)
    article["variants"]=variants
    article["totals"]={
        "physical_qty":sum(int(x.get("physical_qty") or 0) for x in variants),
        "reserved_qty":sum(int(x.get("reserved_qty") or 0) for x in variants),
        "available_qty":sum(int(x.get("available_qty") or 0) for x in variants),
        "proposal_qty":sum(int(x.get("proposal_qty") or 0) for x in variants),
        "allocated_qty":sum(int(x.get("allocated_qty") or 0) for x in variants),
        "unassigned_qty":sum(int(x.get("unassigned_qty") or 0) for x in variants),
    }
    article["woo"]={
        "id":raw.get("id"),
        "name":raw.get("name"),
        "slug":raw.get("slug"),
        "permalink":raw.get("permalink"),
        "type":raw.get("type"),
        "status":raw.get("status"),
        "catalog_visibility":raw.get("catalog_visibility"),
        "sku":raw.get("sku"),
        "price":raw.get("price"),
        "regular_price":raw.get("regular_price"),
        "sale_price":raw.get("sale_price"),
        "date_on_sale_from":raw.get("date_on_sale_from"),
        "date_on_sale_to":raw.get("date_on_sale_to"),
        "on_sale":raw.get("on_sale"),
        "purchasable":raw.get("purchasable"),
        "total_sales":raw.get("total_sales"),
        "virtual":raw.get("virtual"),
        "downloadable":raw.get("downloadable"),
        "tax_status":raw.get("tax_status"),
        "tax_class":raw.get("tax_class"),
        "manage_stock":raw.get("manage_stock"),
        "stock_quantity":raw.get("stock_quantity"),
        "stock_status":raw.get("stock_status"),
        "backorders":raw.get("backorders"),
        "backorders_allowed":raw.get("backorders_allowed"),
        "backordered":raw.get("backordered"),
        "sold_individually":raw.get("sold_individually"),
        "weight":raw.get("weight"),
        "dimensions":raw.get("dimensions") if isinstance(raw.get("dimensions"),dict) else {},
        "shipping_required":raw.get("shipping_required"),
        "shipping_taxable":raw.get("shipping_taxable"),
        "shipping_class":raw.get("shipping_class"),
        "shipping_class_id":raw.get("shipping_class_id"),
        "reviews_allowed":raw.get("reviews_allowed"),
        "average_rating":raw.get("average_rating"),
        "rating_count":raw.get("rating_count"),
        "parent_id":raw.get("parent_id"),
        "date_created":raw.get("date_created"),
        "date_modified":raw.get("date_modified"),
        "short_description":raw.get("short_description"),
        "description":raw.get("description"),
        "categories":raw.get("categories") if isinstance(raw.get("categories"),list) else [],
        "tags":raw.get("tags") if isinstance(raw.get("tags"),list) else [],
        "attributes":raw.get("attributes") if isinstance(raw.get("attributes"),list) else [],
        "images":raw.get("images") if isinstance(raw.get("images"),list) else [],
        "meta_data":raw.get("meta_data") if isinstance(raw.get("meta_data"),list) else [],
    }
    # The complete REST product is kept so the product card can expose every source field on demand.
    article["raw_product"]=raw
    return article


@router.post("/inventory/reconcile", dependencies=auth)
async def inventory_reconcile() -> dict[str, Any]:
    stats = await asyncio.to_thread(_reconcile_inventory_from_orders)
    return {"ok":True, **stats}


@router.get("/inventory/stock", dependencies=auth)
async def inventory_stock(q: str = "", shortage_only: int = 0, limit: int = 5000) -> dict[str, Any]:
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        sql="""SELECT s.* FROM inventory_stock_items s
                 JOIN inventory_articles a ON a.id=s.article_id
                 WHERE s.active=1"""; args=[]
        if q:
            like=f"%{q}%"
            sql += " AND (s.sku LIKE ? OR s.erp_code LIKE ? OR s.color LIKE ? OR s.size LIKE ? OR s.barcode LIKE ? OR a.name LIKE ? OR a.sku LIKE ? OR a.manufacturer LIKE ? OR a.supplier LIKE ?)"
            args += [like]*9
        sql += " ORDER BY a.name,s.color,s.size,s.sku LIMIT ?"; args.append(max(1,min(int(limit),10000)))
        items=[_stock_item_row(conn,r) for r in conn.execute(sql,args).fetchall()]
    if shortage_only: items=[x for x in items if int(x.get("proposal_qty") or 0)>0]
    return {"ok":True,"items":items}


@router.get("/inventory/articles", dependencies=auth)
async def inventory_articles(q: str = "", shortage_only: int = 0, limit: int = 5000) -> dict[str, Any]:
    """Return the synced article master independently from stock-item creation.

    The Warenwirtschaft article list must not disappear just because a WooCommerce
    product currently has no colour/size stock rows. Stock figures are aggregated
    when variants exist, while article master records remain visible with zeroes.
    """
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        sql = """
            SELECT
                a.id AS article_id,
                a.name AS article,
                a.sku AS article_sku,
                a.manufacturer,
                a.supplier,
                a.image_url,
                a.woo_product_id,
                COUNT(s.id) AS variant_count,
                COALESCE(SUM(s.physical_qty),0) AS physical_qty,
                COALESCE(SUM(s.reserved_qty),0) AS reserved_qty,
                COALESCE(SUM(s.physical_qty-s.reserved_qty),0) AS available_qty,
                COALESCE((
                    SELECT SUM(CASE WHEN p.status='open' AND p.quantity>0 THEN p.quantity ELSE 0 END)
                    FROM purchase_proposals p
                    JOIN inventory_stock_items ps ON ps.id=p.stock_item_id
                    WHERE ps.article_id=a.id AND ps.active=1
                ),0) AS proposal_qty,
                COALESCE((
                    SELECT SUM(CASE WHEN po.status IN ('ordered','partial') AND po.ordered_qty>po.received_qty
                                    THEN po.ordered_qty-po.received_qty ELSE 0 END)
                    FROM purchase_order_lines po
                    JOIN inventory_stock_items os ON os.id=po.stock_item_id
                    WHERE os.article_id=a.id AND os.active=1
                ),0) AS on_order_qty,
                GROUP_CONCAT(DISTINCT NULLIF(s.color,'')) AS colors_csv,
                GROUP_CONCAT(DISTINCT NULLIF(s.size,'')) AS sizes_csv
            FROM inventory_articles a
            LEFT JOIN inventory_stock_items s ON s.article_id=a.id AND s.active=1
            WHERE 1=1
        """
        args: list[Any] = []
        if q:
            like = f"%{q}%"
            sql += """ AND (
                a.name LIKE ? OR a.sku LIKE ? OR a.manufacturer LIKE ? OR a.supplier LIKE ?
                OR EXISTS (
                    SELECT 1 FROM inventory_stock_items sx
                    WHERE sx.article_id=a.id AND sx.active=1
                      AND (sx.sku LIKE ? OR sx.erp_code LIKE ? OR sx.color LIKE ? OR sx.size LIKE ? OR sx.barcode LIKE ?)
                )
            )"""
            args += [like] * 9
        sql += " GROUP BY a.id ORDER BY a.name COLLATE NOCASE, a.sku COLLATE NOCASE LIMIT ?"
        args.append(max(1, min(int(limit), 10000)))
        items = []
        for row in conn.execute(sql, args).fetchall():
            d = dict(row)
            d["physical_qty"] = int(d.get("physical_qty") or 0)
            d["reserved_qty"] = int(d.get("reserved_qty") or 0)
            d["available_qty"] = int(d.get("available_qty") or 0)
            d["proposal_qty"] = int(d.get("proposal_qty") or 0)
            d["on_order_qty"] = int(d.get("on_order_qty") or 0)
            d["variant_count"] = int(d.get("variant_count") or 0)
            d["colors"] = [x for x in str(d.pop("colors_csv", "") or "").split(",") if x]
            d["sizes"] = [x for x in str(d.pop("sizes_csv", "") or "").split(",") if x]
            if shortage_only and d["proposal_qty"] <= 0:
                continue
            items.append(d)
    return {"ok": True, "items": items}


@router.get("/inventory/articles/{article_id}", dependencies=auth)
async def inventory_article(article_id: str) -> dict[str, Any]:
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        article=_inventory_article_detail(conn,article_id)
    return {"ok":True,"article":article}


@router.get("/inventory/summary", dependencies=auth)
async def inventory_summary() -> dict[str, Any]:
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        row=conn.execute("SELECT COUNT(*) n,COALESCE(SUM(physical_qty),0) physical,COALESCE(SUM(reserved_qty),0) reserved FROM inventory_stock_items WHERE active=1").fetchone()
        proposals=conn.execute("SELECT COUNT(*) n,COALESCE(SUM(quantity),0) q FROM purchase_proposals WHERE status='open' AND quantity>0").fetchone()
        allocated=conn.execute("SELECT COALESCE(SUM(quantity),0) q FROM inventory_bin_stock").fetchone()
        on_order=conn.execute("SELECT COALESCE(SUM(CASE WHEN ordered_qty>received_qty THEN ordered_qty-received_qty ELSE 0 END),0) q FROM purchase_order_lines WHERE status IN ('ordered','partial')").fetchone()
    allocated_qty=int(allocated["q"] or 0) if allocated else 0
    on_order_qty=int(on_order["q"] or 0) if on_order else 0
    return {"ok":True,"stock_items":int(row["n"]),"physical":int(row["physical"]),"reserved":int(row["reserved"]),"available":int(row["physical"])-int(row["reserved"]),"allocated":allocated_qty,"unassigned":max(0,int(row["physical"])-allocated_qty),"proposal_items":int(proposals["n"]),"proposal_qty":int(proposals["q"]),"on_order_qty":on_order_qty}


@router.get("/inventory/proposals", dependencies=auth)
async def inventory_proposals() -> dict[str, Any]:
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        rows=conn.execute("SELECT p.* FROM purchase_proposals p WHERE p.status='open' AND p.quantity>0 ORDER BY p.updated_at DESC").fetchall()
        items=[]
        for r in rows:
            stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (r["stock_item_id"],)).fetchone()
            if stock: items.append({**dict(r),"stock":_stock_item_row(conn,stock)})
    return {"ok":True,"items":items}


def _purchase_order_line_data(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    d=dict(row)
    d["remaining_qty"]=max(0,int(d.get("ordered_qty") or 0)-int(d.get("received_qty") or 0))
    stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (str(d.get("stock_item_id") or ""),)).fetchone()
    if stock: d["stock"]=_stock_item_row(conn,stock)
    return d


@router.get("/inventory/purchase-orders", dependencies=auth)
async def inventory_purchase_orders(status: str = "open") -> dict[str, Any]:
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        if status == "all":
            rows=conn.execute("SELECT * FROM purchase_order_lines ORDER BY updated_at DESC").fetchall()
        elif status == "closed":
            rows=conn.execute("SELECT * FROM purchase_order_lines WHERE status IN ('received','cancelled') ORDER BY updated_at DESC").fetchall()
        else:
            rows=conn.execute("SELECT * FROM purchase_order_lines WHERE status IN ('ordered','partial') AND ordered_qty>received_qty ORDER BY ordered_at DESC,updated_at DESC").fetchall()
        items=[_purchase_order_line_data(conn,r) for r in rows]
    return {"ok":True,"items":items}


@router.post("/inventory/proposals/{proposal_id}/order", dependencies=auth)
async def inventory_mark_ordered(proposal_id: str, request: Request) -> dict[str, Any]:
    body=await request.json()
    with _db() as conn:
        p=conn.execute("SELECT * FROM purchase_proposals WHERE id=?", (str(proposal_id),)).fetchone()
        if not p: raise HTTPException(status_code=404,detail="Bestellvorschlag nicht gefunden.")
        qty=max(1,_safe_int((body or {}).get("quantity"),int(p["quantity"] or 0) or 1))
        stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (str(p["stock_item_id"]),)).fetchone()
        if not stock: raise HTTPException(status_code=404,detail="Lagerartikel nicht gefunden.")
        item=_stock_item_row(conn,stock)
        supplier=str((body or {}).get("supplier") or item.get("supplier") or "").strip()
        reference=str((body or {}).get("reference") or "").strip()
        note=str((body or {}).get("note") or "").strip()
        line_id=str(uuid.uuid4()); now=_now()
        conn.execute("INSERT INTO purchase_order_lines(id,stock_item_id,proposal_id,supplier,order_reference,ordered_qty,received_qty,status,note,ordered_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (line_id,str(p["stock_item_id"]),str(p["id"]),supplier,reference,qty,0,"ordered",note,now,now))
        _refresh_stock_totals(conn)
        row=conn.execute("SELECT * FROM purchase_order_lines WHERE id=?", (line_id,)).fetchone()
        return {"ok":True,"line":_purchase_order_line_data(conn,row)}


@router.post("/inventory/purchase-orders/{line_id}/receive", dependencies=auth)
async def inventory_purchase_receive(line_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); note=str((body or {}).get("note") or "").strip()
    with _db() as conn:
        line=conn.execute("SELECT * FROM purchase_order_lines WHERE id=?", (str(line_id),)).fetchone()
        if not line: raise HTTPException(status_code=404,detail="Bestellte Position nicht gefunden.")
        remaining=max(0,int(line["ordered_qty"] or 0)-int(line["received_qty"] or 0))
        if remaining<=0: raise HTTPException(status_code=409,detail="Diese bestellte Position ist bereits vollständig eingegangen.")
        qty=max(1,_safe_int((body or {}).get("quantity"),remaining))
        if qty>remaining: raise HTTPException(status_code=409,detail=f"Es sind nur noch {remaining} Stück offen.")
        stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (str(line["stock_item_id"]),)).fetchone()
        if not stock: raise HTTPException(status_code=404,detail="Lagerartikel nicht gefunden.")
        now=_now(); received=int(line["received_qty"] or 0)+qty; status="received" if received>=int(line["ordered_qty"] or 0) else "partial"
        conn.execute("UPDATE purchase_order_lines SET received_qty=?,status=?,updated_at=? WHERE id=?", (received,status,now,str(line_id)))
        conn.execute("UPDATE inventory_stock_items SET physical_qty=physical_qty+?,updated_at=? WHERE id=?", (qty,now,str(line["stock_item_id"])))
        ref=str(line["order_reference"] or line_id)
        conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at) VALUES(?,?,?,?,?,?,?)", (str(line["stock_item_id"]),"receipt",qty,"purchase_order",ref,note or "Wareneingang bestellter Ware",now))
        _refresh_stock_totals(conn)
        stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (str(line["stock_item_id"]),)).fetchone()
        line=conn.execute("SELECT * FROM purchase_order_lines WHERE id=?", (str(line_id),)).fetchone()
        return {"ok":True,"item":_stock_item_row(conn,stock),"line":_purchase_order_line_data(conn,line),"labels":qty}


@router.post("/inventory/purchase-orders/{line_id}/cancel", dependencies=auth)
async def inventory_purchase_cancel(line_id: str) -> dict[str, Any]:
    with _db() as conn:
        line=conn.execute("SELECT * FROM purchase_order_lines WHERE id=?", (str(line_id),)).fetchone()
        if not line: raise HTTPException(status_code=404,detail="Bestellte Position nicht gefunden.")
        if int(line["received_qty"] or 0)>0: raise HTTPException(status_code=409,detail="Bereits teilweise eingegangene Positionen können nicht vollständig storniert werden.")
        conn.execute("UPDATE purchase_order_lines SET status='cancelled',updated_at=? WHERE id=?", (_now(),str(line_id)))
        _refresh_stock_totals(conn)
    return {"ok":True}


@router.post("/inventory/stock/{stock_item_id}/receipt", dependencies=auth)
async def inventory_receipt(stock_item_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); qty=max(0,_safe_int((body or {}).get("quantity"),0)); note=str((body or {}).get("note") or "").strip(); ref=str((body or {}).get("reference") or "").strip()
    if qty<=0: raise HTTPException(status_code=400,detail="Wareneingangsmenge muss größer als 0 sein.")
    with _db() as conn:
        row=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (stock_item_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Lagerartikel nicht gefunden.")
        conn.execute("UPDATE inventory_stock_items SET physical_qty=physical_qty+?,updated_at=? WHERE id=?", (qty,_now(),stock_item_id))
        conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at) VALUES(?,?,?,?,?,?,?)", (stock_item_id,"receipt",qty,"purchase",ref,note,_now()))
        _refresh_stock_totals(conn); row=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (stock_item_id,)).fetchone(); item=_stock_item_row(conn,row)
    return {"ok":True,"item":item,"labels":qty}


@router.post("/inventory/stock/{stock_item_id}/adjust", dependencies=auth)
async def inventory_adjust(stock_item_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); target=max(0,_safe_int((body or {}).get("physical_qty"),0)); note=str((body or {}).get("note") or "Bestandskorrektur").strip()
    with _db() as conn:
        row=conn.execute("SELECT physical_qty FROM inventory_stock_items WHERE id=?", (stock_item_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Lagerartikel nicht gefunden.")
        delta=target-int(row["physical_qty"] or 0); conn.execute("UPDATE inventory_stock_items SET physical_qty=?,updated_at=? WHERE id=?", (target,_now(),stock_item_id))
        if delta<0:
            allocated=_allocated_qty(conn,stock_item_id)
            excess=max(0,allocated-target)
            if excess: _consume_bin_stock(conn,stock_item_id,excess)
        if delta: conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,note,created_at) VALUES(?,?,?,?,?)", (stock_item_id,"adjustment",delta,note,_now()))
        _refresh_stock_totals(conn); item=_stock_item_row(conn,conn.execute("SELECT * FROM inventory_stock_items WHERE id=?",(stock_item_id,)).fetchone())
    return {"ok":True,"item":item,"delta":delta}


@router.get("/inventory/scan/{barcode}", dependencies=auth)
async def inventory_scan_lookup(barcode: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM inventory_stock_items WHERE barcode=?", (str(barcode).strip().upper(),)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Barcode ist keinem Lagerartikel zugeordnet.")
        return {"ok":True,"item":_stock_item_row(conn,row)}


@router.post("/inventory/production-scan", dependencies=auth)
async def inventory_production_scan(request: Request) -> dict[str, Any]:
    body=await request.json(); barcode=str((body or {}).get("barcode") or "").strip().upper(); task_id=str((body or {}).get("task_id") or "").strip()
    if not barcode or not task_id: raise HTTPException(status_code=400,detail="Barcode und Produktionsschritt werden benötigt.")
    await asyncio.to_thread(_reconcile_inventory_from_orders)
    with _db() as conn:
        stock=conn.execute("SELECT * FROM inventory_stock_items WHERE barcode=?",(barcode,)).fetchone()
        if not stock: raise HTTPException(status_code=404,detail="Barcode ist keinem Lagerartikel zugeordnet.")
    with _base_db() as base:
        task=base.execute("""SELECT t.*,i.sku,i.product_id,i.erp_code,i.color,i.size,i.id base_item_id,i.quantity,o.order_no
                           FROM tasks t JOIN items i ON i.id=t.item_id JOIN orders o ON o.id=t.order_id WHERE t.id=?""",(task_id,)).fetchone()
        if not task: raise HTTPException(status_code=404,detail="Produktionsschritt nicht gefunden.")
        expected=_stock_id(str(task["product_id"] or ""),str(task["sku"] or ""),str(task["erp_code"] or ""),str(task["color"] or ""),str(task["size"] or ""))
        if expected != str(stock["id"]):
            raise HTTPException(status_code=409,detail=f"Falscher Lagerartikel. Erwartet: {task['sku'] or task['product_id']} · {task['color'] or '-'} · {task['size'] or '-'}.")
        if int(task["done_qty"] or 0) >= int(task["target_qty"] or 0): raise HTTPException(status_code=409,detail="Dieser Produktionsschritt ist bereits vollständig.")
    # Book production first. Inventory is only consumed after a successful task booking.
    result = await asyncio.to_thread(_internal_json, f"/api/tasks/{urllib.parse.quote(task_id)}" + "/delta", "POST", {"delta":1}, 30)
    consume_delta=0
    with _base_db() as base:
        max_done=base.execute("SELECT COALESCE(MAX(done_qty),0) d FROM tasks WHERE item_id=?",(str(task["base_item_id"]),)).fetchone()["d"]
    with _db() as conn:
        res=conn.execute("SELECT * FROM inventory_reservations WHERE item_id=? AND status='active'",(str(task["base_item_id"]),)).fetchone()
        consumed=int(res["consumed_qty"] or 0) if res else 0; desired=min(int(task["quantity"] or 0),int(max_done or 0)); consume_delta=max(0,desired-consumed)
        if consume_delta:
            current=conn.execute("SELECT physical_qty FROM inventory_stock_items WHERE id=?",(str(stock["id"]),)).fetchone()
            if int(current["physical_qty"] or 0) < consume_delta:
                # Undo production booking when physical inventory cannot be consumed.
                await asyncio.to_thread(_internal_json, f"/api/tasks/{urllib.parse.quote(task_id)}/delta", "POST", {"delta":-1}, 30)
                raise HTTPException(status_code=409,detail="Kein ausreichender physischer Lagerbestand vorhanden.")
            conn.execute("UPDATE inventory_stock_items SET physical_qty=physical_qty-?,updated_at=? WHERE id=?",(consume_delta,_now(),str(stock["id"])))
            if res: conn.execute("UPDATE inventory_reservations SET consumed_qty=?,updated_at=? WHERE id=?",(desired,_now(),str(res["id"])))
            used_bins=_consume_bin_stock(conn,str(stock["id"]),consume_delta)
            booked=sum(q for _,q in used_bins)
            for source_bin_id,q in used_bins:
                conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at,source_bin_id,target_bin_id) VALUES(?,?,?,?,?,?,?,?,?)",(str(stock["id"]),"production",-q,"order",str(task["order_id"]),f"Produktion {task['order_no']}",_now(),source_bin_id,""))
            if booked<consume_delta:
                conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at,source_bin_id,target_bin_id) VALUES(?,?,?,?,?,?,?,?,?)",(str(stock["id"]),"production",-(consume_delta-booked),"order",str(task["order_id"]),f"Produktion {task['order_no']} · nicht zugeordnet",_now(),"",""))
        _refresh_stock_totals(conn); item=_stock_item_row(conn,conn.execute("SELECT * FROM inventory_stock_items WHERE id=?",(str(stock["id"]),)).fetchone())
    return {"ok":True,"task":result,"stock":item,"consumed":consume_delta}



def _location_code(value: Any, fallback: str = "") -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", text.upper()).strip("-")
    return text[:32] or fallback


def _bin_barcode(bin_id: str) -> str:
    return "HCA-BIN-" + re.sub(r"[^A-Za-z0-9]", "", str(bin_id)).upper()[:14]


def _allocated_qty(conn: sqlite3.Connection, stock_item_id: str) -> int:
    row = conn.execute("SELECT COALESCE(SUM(quantity),0) q FROM inventory_bin_stock WHERE stock_item_id=?", (str(stock_item_id),)).fetchone()
    return int(row["q"] or 0) if row else 0


def _bin_stock_rows(conn: sqlite3.Connection, stock_item_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("""
        SELECT bs.quantity,b.id bin_id,b.name bin_name,b.code bin_code,b.barcode bin_barcode,
               r.id rack_id,r.name rack_name,r.code rack_code,
               w.id warehouse_id,w.name warehouse_name,w.code warehouse_code
        FROM inventory_bin_stock bs
        JOIN inventory_bins b ON b.id=bs.bin_id
        JOIN inventory_racks r ON r.id=b.rack_id
        JOIN inventory_warehouses w ON w.id=b.warehouse_id
        WHERE bs.stock_item_id=? AND bs.quantity<>0 AND b.active=1 AND r.active=1 AND w.active=1
        ORDER BY w.name,r.sort_order,r.name,b.sort_order,b.name
    """, (str(stock_item_id),)).fetchall()
    return [dict(r) for r in rows]


def _bin_detail(conn: sqlite3.Connection, bin_id: str) -> dict[str, Any]:
    row = conn.execute("""
        SELECT b.*,r.name rack_name,r.code rack_code,w.name warehouse_name,w.code warehouse_code
        FROM inventory_bins b
        JOIN inventory_racks r ON r.id=b.rack_id
        JOIN inventory_warehouses w ON w.id=b.warehouse_id
        WHERE b.id=?
    """, (str(bin_id),)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lagerfach nicht gefunden.")
    d = dict(row)
    contents=[]
    for r in conn.execute("SELECT stock_item_id,quantity FROM inventory_bin_stock WHERE bin_id=? AND quantity>0 ORDER BY updated_at DESC", (str(bin_id),)).fetchall():
        stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (str(r["stock_item_id"]),)).fetchone()
        if stock:
            item=_stock_item_row(conn, stock)
            item["bin_qty"]=int(r["quantity"] or 0)
            contents.append(item)
    d["contents"]=contents
    d["quantity"]=sum(int(x.get("bin_qty") or 0) for x in contents)
    return d


def _warehouse_tree_data(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    warehouses=[]
    for w in conn.execute("SELECT * FROM inventory_warehouses WHERE active=1 ORDER BY is_default DESC,name").fetchall():
        wd=dict(w); wd["racks"]=[]; wd["quantity"]=0; wd["bin_count"]=0
        for r in conn.execute("SELECT * FROM inventory_racks WHERE warehouse_id=? AND active=1 ORDER BY sort_order,name", (w["id"],)).fetchall():
            rd=dict(r); rd["bins"]=[]; rd["quantity"]=0
            for b in conn.execute("SELECT * FROM inventory_bins WHERE rack_id=? AND active=1 ORDER BY sort_order,name", (r["id"],)).fetchall():
                bd=dict(b)
                q=conn.execute("SELECT COALESCE(SUM(quantity),0) q FROM inventory_bin_stock WHERE bin_id=?", (b["id"],)).fetchone()
                bd["quantity"]=int(q["q"] or 0) if q else 0
                rd["quantity"] += bd["quantity"]; wd["quantity"] += bd["quantity"]; wd["bin_count"] += 1
                rd["bins"].append(bd)
            wd["racks"].append(rd)
        warehouses.append(wd)
    return warehouses


def _resolve_inventory_barcode(conn: sqlite3.Connection, barcode: str) -> dict[str, Any]:
    code=str(barcode or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Barcode fehlt.")
    stock=conn.execute("SELECT * FROM inventory_stock_items WHERE UPPER(barcode)=? AND active=1", (code,)).fetchone()
    if stock:
        item=_stock_item_row(conn,stock)
        item["bins"]=_bin_stock_rows(conn,str(stock["id"]))
        item["allocated_qty"]=_allocated_qty(conn,str(stock["id"]))
        item["unassigned_qty"]=max(0,int(item.get("physical_qty") or 0)-int(item["allocated_qty"]))
        return {"type":"stock_item","item":item}
    b=conn.execute("SELECT id FROM inventory_bins WHERE UPPER(barcode)=? AND active=1", (code,)).fetchone()
    if b:
        return {"type":"bin","bin":_bin_detail(conn,str(b["id"]))}
    raise HTTPException(status_code=404, detail="Barcode ist weder einem Artikel noch einem Lagerfach zugeordnet.")


def _putaway(conn: sqlite3.Connection, stock_item_id: str, bin_id: str, quantity: int, note: str = "", user_label: str = "") -> dict[str, Any]:
    qty=max(0,int(quantity or 0))
    if qty<=0:
        raise HTTPException(status_code=400, detail="Menge muss größer als 0 sein.")
    stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=? AND active=1", (str(stock_item_id),)).fetchone()
    if not stock:
        raise HTTPException(status_code=404, detail="Lagerartikel nicht gefunden.")
    b=conn.execute("SELECT id FROM inventory_bins WHERE id=? AND active=1", (str(bin_id),)).fetchone()
    if not b:
        raise HTTPException(status_code=404, detail="Lagerfach nicht gefunden.")
    allocated=_allocated_qty(conn,str(stock_item_id)); physical=int(stock["physical_qty"] or 0); unassigned=max(0,physical-allocated)
    if qty>unassigned:
        raise HTTPException(status_code=409, detail=f"Nur {unassigned} Stück sind noch keinem Fach zugeordnet. Erst Wareneingang buchen oder Menge reduzieren.")
    now=_now()
    conn.execute("""INSERT INTO inventory_bin_stock(bin_id,stock_item_id,quantity,updated_at) VALUES(?,?,?,?)
                    ON CONFLICT(bin_id,stock_item_id) DO UPDATE SET quantity=quantity+excluded.quantity,updated_at=excluded.updated_at""", (str(bin_id),str(stock_item_id),qty,now))
    conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at,source_bin_id,target_bin_id,user_label) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (str(stock_item_id),"putaway",qty,"bin",str(bin_id),str(note or "Einlagerung"),now,"",str(bin_id),str(user_label or "")))
    item=_stock_item_row(conn,stock); item["bins"]=_bin_stock_rows(conn,str(stock_item_id)); item["allocated_qty"]=_allocated_qty(conn,str(stock_item_id)); item["unassigned_qty"]=max(0,int(item.get("physical_qty") or 0)-int(item["allocated_qty"]))
    return item


def _relocate(conn: sqlite3.Connection, stock_item_id: str, source_bin_id: str, target_bin_id: str, quantity: int, note: str = "", user_label: str = "") -> dict[str, Any]:
    qty=max(0,int(quantity or 0))
    if qty<=0:
        raise HTTPException(status_code=400, detail="Menge muss größer als 0 sein.")
    if str(source_bin_id)==str(target_bin_id):
        raise HTTPException(status_code=400, detail="Quell- und Zielfach sind identisch.")
    src=conn.execute("SELECT quantity FROM inventory_bin_stock WHERE bin_id=? AND stock_item_id=?", (str(source_bin_id),str(stock_item_id))).fetchone()
    if not src or int(src["quantity"] or 0)<qty:
        raise HTTPException(status_code=409, detail="Im Quellfach liegt nicht genügend Bestand dieses Artikels.")
    if not conn.execute("SELECT id FROM inventory_bins WHERE id=? AND active=1", (str(target_bin_id),)).fetchone():
        raise HTTPException(status_code=404, detail="Zielfach nicht gefunden.")
    now=_now()
    conn.execute("UPDATE inventory_bin_stock SET quantity=quantity-?,updated_at=? WHERE bin_id=? AND stock_item_id=?", (qty,now,str(source_bin_id),str(stock_item_id)))
    conn.execute("DELETE FROM inventory_bin_stock WHERE bin_id=? AND stock_item_id=? AND quantity<=0", (str(source_bin_id),str(stock_item_id)))
    conn.execute("""INSERT INTO inventory_bin_stock(bin_id,stock_item_id,quantity,updated_at) VALUES(?,?,?,?)
                    ON CONFLICT(bin_id,stock_item_id) DO UPDATE SET quantity=quantity+excluded.quantity,updated_at=excluded.updated_at""", (str(target_bin_id),str(stock_item_id),qty,now))
    conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at,source_bin_id,target_bin_id,user_label) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (str(stock_item_id),"relocation",qty,"bin",str(target_bin_id),str(note or "Umlagerung"),now,str(source_bin_id),str(target_bin_id),str(user_label or "")))
    stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (str(stock_item_id),)).fetchone(); item=_stock_item_row(conn,stock); item["bins"]=_bin_stock_rows(conn,str(stock_item_id)); item["allocated_qty"]=_allocated_qty(conn,str(stock_item_id)); item["unassigned_qty"]=max(0,int(item.get("physical_qty") or 0)-int(item["allocated_qty"]))
    return item


def _consume_bin_stock(conn: sqlite3.Connection, stock_item_id: str, quantity: int) -> list[tuple[str,int]]:
    remaining=max(0,int(quantity or 0)); used=[]
    if not remaining: return used
    rows=conn.execute("SELECT bin_id,quantity FROM inventory_bin_stock WHERE stock_item_id=? AND quantity>0 ORDER BY quantity DESC,updated_at", (str(stock_item_id),)).fetchall()
    now=_now()
    for r in rows:
        if remaining<=0: break
        take=min(remaining,int(r["quantity"] or 0))
        if take<=0: continue
        conn.execute("UPDATE inventory_bin_stock SET quantity=quantity-?,updated_at=? WHERE bin_id=? AND stock_item_id=?", (take,now,str(r["bin_id"]),str(stock_item_id)))
        conn.execute("DELETE FROM inventory_bin_stock WHERE bin_id=? AND stock_item_id=? AND quantity<=0", (str(r["bin_id"]),str(stock_item_id)))
        used.append((str(r["bin_id"]),take)); remaining-=take
    return used


@router.get("/inventory/warehouses", dependencies=auth)
async def inventory_warehouses() -> dict[str, Any]:
    with _db() as conn:
        return {"ok":True,"warehouses":_warehouse_tree_data(conn)}


@router.post("/inventory/warehouses", dependencies=auth)
async def inventory_warehouse_create(request: Request) -> dict[str, Any]:
    body=await request.json(); name=str((body or {}).get("name") or "").strip(); code=_location_code((body or {}).get("code"), _location_code(name,"LAGER"))
    if not name: raise HTTPException(status_code=400,detail="Lagername fehlt.")
    now=_now(); wid=str(uuid.uuid4())
    with _db() as conn:
        if conn.execute("SELECT id FROM inventory_warehouses WHERE UPPER(code)=? AND active=1", (code.upper(),)).fetchone(): raise HTTPException(status_code=409,detail="Lagercode existiert bereits.")
        conn.execute("INSERT INTO inventory_warehouses(id,name,code,is_default,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (wid,name,code,0,1,now,now))
        return {"ok":True,"warehouse":dict(conn.execute("SELECT * FROM inventory_warehouses WHERE id=?",(wid,)).fetchone())}


@router.put("/inventory/warehouses/{warehouse_id}", dependencies=auth)
async def inventory_warehouse_update(warehouse_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); name=str((body or {}).get("name") or "").strip(); code=_location_code((body or {}).get("code"),_location_code(name,"LAGER"))
    if not name: raise HTTPException(status_code=400,detail="Lagername fehlt.")
    with _db() as conn:
        if not conn.execute("SELECT id FROM inventory_warehouses WHERE id=?",(warehouse_id,)).fetchone(): raise HTTPException(status_code=404,detail="Lager nicht gefunden.")
        conn.execute("UPDATE inventory_warehouses SET name=?,code=?,updated_at=? WHERE id=?",(name,code,_now(),warehouse_id)); return {"ok":True}


@router.delete("/inventory/warehouses/{warehouse_id}", dependencies=auth)
async def inventory_warehouse_delete(warehouse_id: str) -> dict[str, Any]:
    with _db() as conn:
        if conn.execute("SELECT id FROM inventory_racks WHERE warehouse_id=? AND active=1 LIMIT 1",(warehouse_id,)).fetchone(): raise HTTPException(status_code=409,detail="Lager enthält noch Regale.")
        conn.execute("UPDATE inventory_warehouses SET active=0,updated_at=? WHERE id=?",(_now(),warehouse_id)); return {"ok":True}


@router.post("/inventory/warehouses/{warehouse_id}/racks", dependencies=auth)
async def inventory_rack_create(warehouse_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); name=str((body or {}).get("name") or "").strip(); code=_location_code((body or {}).get("code"),_location_code(name,"REGAL")); sort_order=_safe_int((body or {}).get("sort_order"),0)
    if not name: raise HTTPException(status_code=400,detail="Regalname fehlt.")
    with _db() as conn:
        if not conn.execute("SELECT id FROM inventory_warehouses WHERE id=? AND active=1",(warehouse_id,)).fetchone(): raise HTTPException(status_code=404,detail="Lager nicht gefunden.")
        rid=str(uuid.uuid4()); now=_now(); conn.execute("INSERT INTO inventory_racks(id,warehouse_id,name,code,sort_order,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(rid,warehouse_id,name,code,sort_order,1,now,now)); return {"ok":True,"rack":dict(conn.execute("SELECT * FROM inventory_racks WHERE id=?",(rid,)).fetchone())}


@router.put("/inventory/racks/{rack_id}", dependencies=auth)
async def inventory_rack_update(rack_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); name=str((body or {}).get("name") or "").strip(); code=_location_code((body or {}).get("code"),_location_code(name,"REGAL")); sort_order=_safe_int((body or {}).get("sort_order"),0)
    if not name: raise HTTPException(status_code=400,detail="Regalname fehlt.")
    with _db() as conn:
        if not conn.execute("SELECT id FROM inventory_racks WHERE id=?",(rack_id,)).fetchone(): raise HTTPException(status_code=404,detail="Regal nicht gefunden.")
        conn.execute("UPDATE inventory_racks SET name=?,code=?,sort_order=?,updated_at=? WHERE id=?",(name,code,sort_order,_now(),rack_id)); return {"ok":True}


@router.delete("/inventory/racks/{rack_id}", dependencies=auth)
async def inventory_rack_delete(rack_id: str) -> dict[str, Any]:
    with _db() as conn:
        if conn.execute("SELECT id FROM inventory_bins WHERE rack_id=? AND active=1 LIMIT 1",(rack_id,)).fetchone(): raise HTTPException(status_code=409,detail="Regal enthält noch Fächer.")
        conn.execute("UPDATE inventory_racks SET active=0,updated_at=? WHERE id=?",(_now(),rack_id)); return {"ok":True}


@router.post("/inventory/racks/{rack_id}/bins", dependencies=auth)
async def inventory_bin_create(rack_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); name=str((body or {}).get("name") or "").strip(); code=_location_code((body or {}).get("code"),_location_code(name,"FACH")); sort_order=_safe_int((body or {}).get("sort_order"),0)
    if not name: raise HTTPException(status_code=400,detail="Fachname fehlt.")
    with _db() as conn:
        rack=conn.execute("SELECT * FROM inventory_racks WHERE id=? AND active=1",(rack_id,)).fetchone()
        if not rack: raise HTTPException(status_code=404,detail="Regal nicht gefunden.")
        bid=str(uuid.uuid4()); barcode=_bin_barcode(bid); now=_now(); conn.execute("INSERT INTO inventory_bins(id,warehouse_id,rack_id,name,code,barcode,sort_order,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(bid,str(rack["warehouse_id"]),rack_id,name,code,barcode,sort_order,1,now,now)); return {"ok":True,"bin":_bin_detail(conn,bid)}


@router.put("/inventory/bins/{bin_id}", dependencies=auth)
async def inventory_bin_update(bin_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); name=str((body or {}).get("name") or "").strip(); code=_location_code((body or {}).get("code"),_location_code(name,"FACH")); sort_order=_safe_int((body or {}).get("sort_order"),0)
    if not name: raise HTTPException(status_code=400,detail="Fachname fehlt.")
    with _db() as conn:
        if not conn.execute("SELECT id FROM inventory_bins WHERE id=?",(bin_id,)).fetchone(): raise HTTPException(status_code=404,detail="Fach nicht gefunden.")
        conn.execute("UPDATE inventory_bins SET name=?,code=?,sort_order=?,updated_at=? WHERE id=?",(name,code,sort_order,_now(),bin_id)); return {"ok":True,"bin":_bin_detail(conn,bin_id)}


@router.delete("/inventory/bins/{bin_id}", dependencies=auth)
async def inventory_bin_delete(bin_id: str) -> dict[str, Any]:
    with _db() as conn:
        q=conn.execute("SELECT COALESCE(SUM(quantity),0) q FROM inventory_bin_stock WHERE bin_id=?",(bin_id,)).fetchone()
        if q and int(q["q"] or 0)>0: raise HTTPException(status_code=409,detail="Fach enthält noch Bestand.")
        conn.execute("UPDATE inventory_bins SET active=0,updated_at=? WHERE id=?",(_now(),bin_id)); return {"ok":True}


@router.get("/inventory/bins/{bin_id}", dependencies=auth)
async def inventory_bin_get(bin_id: str) -> dict[str, Any]:
    with _db() as conn: return {"ok":True,"bin":_bin_detail(conn,bin_id)}


@router.get("/inventory/location-scan/{barcode}", dependencies=auth)
async def inventory_location_scan(barcode: str) -> dict[str, Any]:
    with _db() as conn: return {"ok":True,**_resolve_inventory_barcode(conn,barcode)}


@router.get("/inventory/movements", dependencies=auth)
async def inventory_movements(stock_item_id: str = "", bin_id: str = "", limit: int = 250) -> dict[str, Any]:
    with _db() as conn:
        sql="SELECT * FROM inventory_movements WHERE 1=1"; args=[]
        if stock_item_id: sql+=" AND stock_item_id=?"; args.append(str(stock_item_id))
        if bin_id: sql+=" AND (source_bin_id=? OR target_bin_id=?)"; args.extend([str(bin_id),str(bin_id)])
        sql+=" ORDER BY id DESC LIMIT ?"; args.append(max(1,min(int(limit),2000)))
        items=[]
        for r in conn.execute(sql,args).fetchall():
            d=dict(r); stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?",(str(d.get("stock_item_id") or ""),)).fetchone()
            if stock: d["stock"]=_stock_item_row(conn,stock)
            for key in ("source_bin_id","target_bin_id"):
                bid=str(d.get(key) or "")
                if bid:
                    try: d[key.replace("_id","")]=_bin_detail(conn,bid)
                    except Exception: pass
            items.append(d)
    return {"ok":True,"items":items}


@router.post("/inventory/putaway", dependencies=auth)
async def inventory_putaway(request: Request) -> dict[str, Any]:
    body=await request.json(); item_barcode=str((body or {}).get("item_barcode") or "").strip(); bin_barcode=str((body or {}).get("bin_barcode") or "").strip(); qty=max(1,_safe_int((body or {}).get("quantity"),1)); user_label=str((body or {}).get("user_label") or "").strip()
    with _db() as conn:
        item=_resolve_inventory_barcode(conn,item_barcode); loc=_resolve_inventory_barcode(conn,bin_barcode)
        if item.get("type")!="stock_item": raise HTTPException(status_code=400,detail="Erster Barcode ist kein Artikelbarcode.")
        if loc.get("type")!="bin": raise HTTPException(status_code=400,detail="Zweiter Barcode ist kein Fachbarcode.")
        updated=_putaway(conn,str(item["item"]["id"]),str(loc["bin"]["id"]),qty,"Einlagerung per Scan",user_label); return {"ok":True,"item":updated,"bin":_bin_detail(conn,str(loc["bin"]["id"])),"quantity":qty}


@router.post("/inventory/manual-putaway", dependencies=auth)
async def inventory_manual_putaway(request: Request) -> dict[str, Any]:
    body=await request.json(); item_barcode=str((body or {}).get("item_barcode") or "").strip(); bin_barcode=str((body or {}).get("bin_barcode") or "").strip(); qty=max(1,_safe_int((body or {}).get("quantity"),1)); user_label=str((body or {}).get("user_label") or "").strip()
    with _db() as conn:
        item=_resolve_inventory_barcode(conn,item_barcode); loc=_resolve_inventory_barcode(conn,bin_barcode)
        if item.get("type")!="stock_item": raise HTTPException(status_code=400,detail="Erster Barcode ist kein Artikelbarcode.")
        if loc.get("type")!="bin": raise HTTPException(status_code=400,detail="Zweiter Barcode ist kein Fachbarcode.")
        sid=str(item["item"]["id"]); bid=str(loc["bin"]["id"]); now=_now()
        conn.execute("UPDATE inventory_stock_items SET physical_qty=physical_qty+?,updated_at=? WHERE id=?", (qty,now,sid))
        conn.execute("""INSERT INTO inventory_bin_stock(bin_id,stock_item_id,quantity,updated_at) VALUES(?,?,?,?)
                        ON CONFLICT(bin_id,stock_item_id) DO UPDATE SET quantity=quantity+excluded.quantity,updated_at=excluded.updated_at""", (bid,sid,qty,now))
        conn.execute("INSERT INTO inventory_movements(stock_item_id,movement_type,quantity,reference_type,reference_id,note,created_at,source_bin_id,target_bin_id,user_label) VALUES(?,?,?,?,?,?,?,?,?,?)", (sid,"manual_receipt",qty,"bin",bid,"Manuelle Einlagerung per Scan",now,"",bid,user_label or "mobile"))
        _refresh_stock_totals(conn)
        stock=conn.execute("SELECT * FROM inventory_stock_items WHERE id=?", (sid,)).fetchone(); updated=_stock_item_row(conn,stock); updated["bins"]=_bin_stock_rows(conn,sid); updated["allocated_qty"]=_allocated_qty(conn,sid); updated["unassigned_qty"]=max(0,int(updated.get("physical_qty") or 0)-int(updated["allocated_qty"]))
        return {"ok":True,"item":updated,"bin":_bin_detail(conn,bid),"quantity":qty}


@router.post("/inventory/relocate", dependencies=auth)
async def inventory_relocate(request: Request) -> dict[str, Any]:
    body=await request.json(); item_barcode=str((body or {}).get("item_barcode") or "").strip(); source_barcode=str((body or {}).get("source_bin_barcode") or "").strip(); target_barcode=str((body or {}).get("target_bin_barcode") or "").strip(); qty=max(1,_safe_int((body or {}).get("quantity"),1)); user_label=str((body or {}).get("user_label") or "").strip()
    with _db() as conn:
        item=_resolve_inventory_barcode(conn,item_barcode); src=_resolve_inventory_barcode(conn,source_barcode); dst=_resolve_inventory_barcode(conn,target_barcode)
        if item.get("type")!="stock_item" or src.get("type")!="bin" or dst.get("type")!="bin": raise HTTPException(status_code=400,detail="Artikel-, Quellfach- oder Zielfachbarcode ist ungültig.")
        updated=_relocate(conn,str(item["item"]["id"]),str(src["bin"]["id"]),str(dst["bin"]["id"]),qty,"Umlagerung per Scan",user_label); return {"ok":True,"item":updated,"source":_bin_detail(conn,str(src["bin"]["id"])),"target":_bin_detail(conn,str(dst["bin"]["id"])),"quantity":qty}



def _cleanup_mobile_pairings() -> None:
    now = time.time()
    for token, expires_at in list(MOBILE_PAIRINGS.items()):
        if expires_at <= now:
            MOBILE_PAIRINGS.pop(token, None)


def _mobile_device_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _mobile_device_valid(token: str) -> bool:
    token=str(token or "").strip()
    if not token: return False
    with _db() as conn:
        row=conn.execute("SELECT active FROM mobile_devices WHERE token_hash=?", (_mobile_device_hash(token),)).fetchone()
        if not row or not int(row["active"] or 0): return False
        conn.execute("UPDATE mobile_devices SET last_seen_at=? WHERE token_hash=?", (_now(),_mobile_device_hash(token)))
    return True


def _mobile_json_response(data: dict[str, Any], device_token: str = "", clear_cookie: bool = False) -> Response:
    res=Response(_json(data), media_type="application/json")
    if clear_cookie:
        res.delete_cookie("hca_mobile_device", path="/api/hca-shared")
    elif device_token:
        res.set_cookie("hca_mobile_device", device_token, max_age=31536000, httponly=True, secure=True, samesite="strict", path="/api/hca-shared")
    return res


@router.post("/mobile/pairing/create", dependencies=auth)
async def mobile_pairing_create() -> dict[str, Any]:
    _cleanup_mobile_pairings()
    token = uuid.uuid4().hex[:12].upper()
    MOBILE_PAIRINGS[token] = time.time() + MOBILE_PAIRING_TTL_SECONDS
    return {"ok": True, "token": token, "expires_in": MOBILE_PAIRING_TTL_SECONDS}


@router.post("/mobile")
async def mobile_pairing_redeem(request: Request) -> Response:
    body = await request.json()
    body=body or {}
    action=str(body.get("action") or "").strip().lower()
    pair_token = str(body.get("pair_token") or "").strip().upper()
    supplied_device = str(body.get("device_token") or "").strip()
    cookie_device = str(request.cookies.get("hca_mobile_device") or "").strip()
    device_token=supplied_device or cookie_device
    _cleanup_mobile_pairings()

    if action == "revoke":
        if device_token:
            with _db() as conn:
                conn.execute("UPDATE mobile_devices SET active=0,last_seen_at=? WHERE token_hash=?", (_now(),_mobile_device_hash(device_token)))
        return _mobile_json_response({"ok":True}, clear_cookie=True)

    if pair_token:
        expires_at = MOBILE_PAIRINGS.pop(pair_token, None)
        if not expires_at or expires_at <= time.time():
            raise HTTPException(status_code=401, detail="Pairing-Code ist ungültig oder abgelaufen.")
        device_token=secrets.token_urlsafe(32)
        now=_now(); ua=str(request.headers.get("user-agent") or "")[:500]
        with _db() as conn:
            conn.execute("INSERT OR REPLACE INTO mobile_devices(token_hash,label,user_agent,active,created_at,last_seen_at) VALUES(?,?,?,?,?,?)", (_mobile_device_hash(device_token),"Mobile-Device",ua,1,now,now))
    elif not _mobile_device_valid(device_token):
        raise HTTPException(status_code=401, detail="Mobile-Device ist nicht verbunden. Bitte erneut per QR-Code koppeln.")

    api_key = str(os.getenv("HCA_API_KEY", "") or "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="HCA API-Schlüssel ist am Server nicht konfiguriert.")
    # API-Key wird nur für diese Browser-Sitzung zurückgegeben und nicht dauerhaft im Mobile-Device gespeichert.
    return _mobile_json_response({"ok": True, "api_key": api_key, "device_token": device_token if pair_token else ""}, device_token=device_token)


# Mobile warehouse app v0.9.40: HCA design, persistent device pairing, manual stock-in and iOS scanner
MOBILE_HTML = r'''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1d1d1b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="HCA Lager">
<link rel="manifest" href="/api/hca-shared/mobile/manifest.webmanifest">
<link rel="apple-touch-icon" href="data:image/png;base64,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">
<title>HCA Lager</title>
<style>
:root{--bg:#f4f4f2;--surface:#fff;--surface2:#f8f8f6;--ink:#1d1d1b;--muted:#72726f;--line:#e2e2de;--brand:#e75303;--brand-soft:#fff0e9;--sidebar:#1d1d1b;--success:#27865f;--danger:#b94a48;--warning:#b87918;--shadow:0 14px 36px rgba(25,25,22,.08);--radius:18px;font-family:"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;color:var(--ink);background:var(--bg)}
*{box-sizing:border-box}html,body{min-height:100%;background:var(--bg)}body{margin:0;color:var(--ink);-webkit-font-smoothing:antialiased}button,input{font:inherit}.hidden{display:none!important}
.app{max-width:760px;margin:0 auto;min-height:100vh;padding:0 14px calc(34px + env(safe-area-inset-bottom));background:var(--bg)}
.mobile-head{margin:0 -14px 18px;padding:calc(12px + env(safe-area-inset-top)) 18px 13px;background:var(--sidebar);color:#fff;display:flex;align-items:center;justify-content:space-between;gap:12px;box-shadow:0 8px 26px rgba(0,0,0,.15)}
.brand{display:flex;align-items:center;gap:12px;min-width:0}.brand-logo{width:52px;height:52px;flex:0 0 52px;object-fit:contain}.brand-copy{min-width:0;line-height:1.08}.brand-copy strong{display:block;font-size:12px;letter-spacing:1.25px;white-space:nowrap}.brand-copy span{display:block;margin-top:4px;color:#cfcfc9;font-size:12px;letter-spacing:.55px}.mobile-badge{white-space:nowrap;border:1px solid #494943;border-radius:999px;padding:7px 9px;color:#d9d9d3;font-size:11px;font-weight:800}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:17px;margin:13px 0;box-shadow:var(--shadow)}.eyebrow{font-size:11px;font-weight:850;letter-spacing:1.2px;color:var(--brand);text-transform:uppercase}.step{font-weight:850;font-size:19px;margin:4px 0 8px}.small{font-size:13px;line-height:1.45;color:var(--muted)}
.mode-nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:0 0 13px}.btn{min-height:46px;border:1px solid var(--line);border-radius:12px;padding:11px 13px;font-weight:760;font-size:14px;background:var(--surface);color:var(--ink);cursor:pointer;-webkit-tap-highlight-color:transparent}.btn:active{transform:translateY(1px)}.btn.primary,.mode.active{background:var(--brand);border-color:var(--brand);color:#171714}.btn.dark{background:var(--sidebar);border-color:var(--sidebar);color:#fff}.btn.good{background:var(--success);border-color:var(--success);color:#fff}.btn.warn{background:var(--warning);border-color:var(--warning);color:#fff}.mode{padding:11px 7px;font-size:13px;line-height:1.15}.mode.active{box-shadow:0 5px 16px rgba(231,83,3,.20)}
.scanrow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:stretch}.scanrow input,.login input,.qty{border:1px solid #cfcfca;border-radius:12px;background:#fff;color:var(--ink);outline:none}.scanrow input{min-width:0;padding:14px;font-size:17px}.scanrow input:focus,.login input:focus,.qty:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(231,83,3,.10)}.scanrow .btn{min-width:104px}.login input{width:100%;padding:14px;margin:10px 0 8px;font-size:16px}.login-actions{display:grid;grid-template-columns:1fr auto;gap:8px}.status{min-height:22px;margin-top:9px;font-size:13px;font-weight:700}.ok{color:var(--success)}.err{color:var(--danger)}
.info{background:var(--surface2);border:1px solid #ecece8;border-radius:12px;padding:12px;margin:12px 0}.info.warning{background:#fff8ed;border-color:#f0d4aa}.info b{font-size:15px}.qty{display:block;width:120px;padding:11px;margin:5px 0 14px;font-size:17px}.contentList{display:grid;gap:7px;margin-top:10px}.contentItem{padding:10px 11px;background:#fff;border:1px solid #ecece8;border-radius:10px;display:flex;justify-content:space-between;gap:10px;align-items:center}.footer-card{box-shadow:none;background:transparent;border-style:dashed}.footer-card .btn{margin-top:12px}
#cameraWrap{position:fixed;inset:0;background:#060606;z-index:100;display:flex;flex-direction:column;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}.camera-head{height:64px;flex:0 0 64px;background:rgba(29,29,27,.98);color:#fff;padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #343431}.camera-title{font-weight:850}.camera-title small{display:block;margin-top:3px;color:#bdbdb7;font-size:11px;font-weight:600}.camera-close{border:1px solid #565650;background:transparent;color:#fff;border-radius:10px;padding:9px 12px;font-weight:750}.camera-stage{position:relative;min-height:0;flex:1;overflow:hidden;background:#000}#camera{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#000}.scan-shade{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.38) 0,rgba(0,0,0,.20) 28%,transparent 28%,transparent 72%,rgba(0,0,0,.25) 72%,rgba(0,0,0,.42) 100%);pointer-events:none}.scan-frame{position:absolute;left:7%;right:7%;top:32%;height:34%;border:2px solid rgba(255,255,255,.82);border-radius:16px;pointer-events:none}.scan-frame:before{content:"";position:absolute;left:7%;right:7%;top:49%;height:3px;background:var(--brand);border-radius:10px;box-shadow:0 0 10px rgba(231,83,3,.65)}.scan-corners{position:absolute;inset:-2px;border-radius:16px;background:linear-gradient(var(--brand),var(--brand)) left top/34px 4px no-repeat,linear-gradient(var(--brand),var(--brand)) left top/4px 34px no-repeat,linear-gradient(var(--brand),var(--brand)) right top/34px 4px no-repeat,linear-gradient(var(--brand),var(--brand)) right top/4px 34px no-repeat,linear-gradient(var(--brand),var(--brand)) left bottom/34px 4px no-repeat,linear-gradient(var(--brand),var(--brand)) left bottom/4px 34px no-repeat,linear-gradient(var(--brand),var(--brand)) right bottom/34px 4px no-repeat,linear-gradient(var(--brand),var(--brand)) right bottom/4px 34px no-repeat}.camera-status{position:absolute;left:16px;right:16px;bottom:18px;padding:11px 13px;border-radius:12px;background:rgba(29,29,27,.86);backdrop-filter:blur(8px);color:#fff;text-align:center;font-size:13px;font-weight:700}.camera-status.good{background:rgba(39,134,95,.92)}.camera-status.warn{background:rgba(184,121,24,.92)}
@media(max-width:520px){.app{padding-left:12px;padding-right:12px}.mobile-head{margin-left:-12px;margin-right:-12px}.scanrow{grid-template-columns:1fr}.scanrow .btn{width:100%}.login-actions{grid-template-columns:1fr}.brand-copy strong{font-size:11px}.mobile-badge{display:none}.card{padding:15px}}
</style>
</head>
<body>
<div class="app">
<header class="mobile-head"><div class="brand"><img class="brand-logo" src="data:image/png;base64,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" alt="Werbestudio Königswinter"><div class="brand-copy"><strong>HCA PRODUKTIONSMANAGER</strong><span>Lager · Mobile-Device</span></div></div><span class="mobile-badge">v0.9.40</span></header>
<div id="login" class="card login"><div class="eyebrow">Verbindung</div><div class="step">Mobile-Device verbinden</div><div class="small">Bitte in HCA unter Einstellungen → „Mobile-Device verbinden“ einen QR-Code erzeugen und mit der Kamera dieses Geräts öffnen. Danach bleibt das Gerät gekoppelt.</div><input id="key" type="password" placeholder="HCA API-Schlüssel (nur Fallback)"><div class="login-actions"><button class="btn primary" id="saveKey">API-Schlüssel verwenden</button><button class="btn" id="pasteKey">Einfügen</button></div><div id="loginStatus" class="status"></div></div>
<div id="main" class="hidden"><nav class="mode-nav"><button class="btn mode active" data-mode="putaway">Wareneingang einlagern</button><button class="btn mode" data-mode="manual">Manuell einlagern</button><button class="btn mode" data-mode="relocate">Umlagern</button><button class="btn mode" data-mode="check">Bestand prüfen</button></nav><div id="flow" class="card"></div><div class="card footer-card"><div class="small"><b>Web-App:</b> In Safari „Teilen“ → „Zum Home-Bildschirm“. Die Kopplung wird als Mobile-Device gespeichert; der lange API-Schlüssel muss nicht erneut eingegeben werden.</div><button class="btn" id="resetConnection">Verbindung zurücksetzen</button></div></div>
</div>
<div id="cameraWrap" class="hidden"><div class="camera-head"><div class="camera-title">Barcode scannen<small>HCA Lager</small></div><button class="camera-close" id="cameraCancel">Abbrechen</button></div><div class="camera-stage"><video id="camera" playsinline webkit-playsinline autoplay muted></video><div class="scan-shade"></div><div class="scan-frame"><div class="scan-corners"></div></div><div id="cameraStatus" class="camera-status">Kamera wird gestartet …</div></div></div>
<script>
const $=s=>document.querySelector(s);
let apiKey='',deviceToken=localStorage.getItem('hcaMobileDeviceToken')||'',manualKey=localStorage.getItem('hcaMobileKey')||'',mode='putaway',state={},scanCallback=null,stream=null,detector=null,raf=0,zxingControls=null,zxingReader=null,zxingLoadPromise=null,scanHintTimer=0,lastDetected='';
function headers(){const h={'Content-Type':'application/json'};if(apiKey)h['X-HCA-Key']=apiKey;return h}
async function api(path,opt={}){const r=await fetch('/api/hca-shared'+path,{...opt,headers:{...headers(),...(opt.headers||{})}});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||d.error||('HTTP '+r.status));return d}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function itemText(x){return `${x.article||x.sku||'Artikel'} · ${x.color||'-'} · ${x.size||'-'}`}
function showMain(){document.querySelector('#login').classList.add('hidden');document.querySelector('#main').classList.remove('hidden');document.querySelector('#loginStatus').textContent='';render()}
function showLogin(msg=''){document.querySelector('#login').classList.remove('hidden');document.querySelector('#main').classList.add('hidden');const st=$('#loginStatus');st.textContent=msg;st.className='status'+(msg?' err':'')}
async function testSession(){try{await api('/inventory/warehouses');showMain();return true}catch(e){showLogin(e.message);return false}}
async function bootstrapDevice(token=''){const st=$('#loginStatus');try{st.textContent='Gespeicherte Verbindung wird geladen …';st.className='status';const r=await fetch('/api/hca-shared/mobile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(token?{device_token:token}:{})});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||d.error||('HTTP '+r.status));apiKey=String(d.api_key||'').trim();if(!apiKey)throw new Error('Mobile-Sitzung konnte nicht aufgebaut werden.');if(token){deviceToken=token;localStorage.setItem('hcaMobileDeviceToken',token)}await testSession();return true}catch(e){if(manualKey){apiKey=manualKey;if(await testSession())return true}showLogin(e.message);return false}}
async function redeemPairing(token){const st=$('#loginStatus');try{st.textContent='Mobile-Device wird verbunden …';st.className='status';const r=await fetch('/api/hca-shared/mobile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pair_token:token})});let d={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||d.error||('HTTP '+r.status));apiKey=String(d.api_key||'').trim();deviceToken=String(d.device_token||'').trim();if(!apiKey||!deviceToken)throw new Error('Die Gerätekopplung konnte nicht abgeschlossen werden.');localStorage.setItem('hcaMobileDeviceToken',deviceToken);localStorage.removeItem('hcaMobileKey');manualKey='';history.replaceState(null,'',location.pathname+location.search+'#device='+encodeURIComponent(deviceToken));await testSession()}catch(e){showLogin(e.message)}}
$('#saveKey').onclick=async()=>{manualKey=$('#key').value.trim();apiKey=manualKey;if(manualKey)localStorage.setItem('hcaMobileKey',manualKey);await testSession()};
$('#pasteKey').onclick=async()=>{try{const t=await navigator.clipboard.readText();$('#key').value=String(t||'').trim()}catch{alert('Zwischenablage konnte nicht gelesen werden. Bitte den Schlüssel in das Feld einfügen.')}};
$('#resetConnection').onclick=async()=>{if(!confirm('Gespeicherte Verbindung auf diesem Mobile-Device zurücksetzen?'))return;try{await fetch('/api/hca-shared/mobile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'revoke',device_token:deviceToken})})}catch{}localStorage.removeItem('hcaMobileDeviceToken');localStorage.removeItem('hcaMobileKey');deviceToken='';manualKey='';apiKey='';history.replaceState(null,'',location.pathname+location.search);$('#key').value='';showLogin('Verbindung wurde zurückgesetzt.')};
$('#key').value=manualKey;
(async()=>{const hash=new URLSearchParams(location.hash.replace(/^#/,''));const pair=hash.get('pair'),fromHash=hash.get('device');if(pair){await redeemPairing(pair);return}if(fromHash){deviceToken=fromHash;localStorage.setItem('hcaMobileDeviceToken',deviceToken)}if(deviceToken){await bootstrapDevice(deviceToken);return}await bootstrapDevice('')})();
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;state={};document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===b));render()});
function scanField(id,label){return `<div class="eyebrow">Barcode</div><div class="step">${label}</div><div class="scanrow"><input id="${id}" autocomplete="off" inputmode="none" placeholder="Barcode scannen …"><button class="btn primary" data-camera="${id}">Kamera</button></div>`}
function bindScan(id,cb){const el=$('#'+id);if(!el)return;el.focus();el.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();const v=el.value.trim();if(v)cb(v)}});const cam=document.querySelector(`[data-camera="${id}"]`);if(cam)cam.onclick=()=>startCamera(code=>{el.value=code;cb(code)})}
function status(t,ok=true){const s=$('#status');if(s){s.textContent=t;s.className='status '+(ok?'ok':'err')}}
async function resolve(code){return await api('/inventory/location-scan/'+encodeURIComponent(code))}
function render(){const f=$('#flow');if(mode==='putaway'){f.innerHTML=putawayHtml();bindPutaway()}else if(mode==='manual'){f.innerHTML=manualHtml();bindManual()}else if(mode==='relocate'){f.innerHTML=relocateHtml();bindRelocate()}else{f.innerHTML=checkHtml();bindCheck()}}
function putawayHtml(){if(!state.item)return '<div class="small">Für bereits am PC gebuchten Wareneingang: Artikel scannen, Menge wählen und anschließend das Lagerfach scannen.</div>'+scanField('itemCode','1. Artikelbarcode scannen')+'<div id="status" class="status"></div>';return `<div class="info"><b>${esc(itemText(state.item))}</b><div class="small">Bestand ${state.item.physical_qty||0} · noch ohne Fach ${state.item.unassigned_qty||0}</div></div><label class="small">Menge</label><input class="qty" id="qty" type="number" min="1" max="${Math.max(1,Number(state.item.unassigned_qty)||1)}" value="${Math.min(Math.max(1,state.qty||1),Math.max(1,Number(state.item.unassigned_qty)||1))}">${scanField('binCode','2. Lagerfach scannen')}<div id="status" class="status"></div><button class="btn" id="reset">Anderen Artikel</button>`}
function bindPutaway(){if(!state.item)bindScan('itemCode',async c=>{try{const d=await resolve(c);if(d.type!=='stock_item')throw new Error('Bitte Artikelbarcode scannen.');if(Number(d.item.unassigned_qty||0)<=0)throw new Error('Für diesen Artikel ist kein gebuchter Wareneingang ohne Lagerfach vorhanden. Für zusätzliche Ware bitte „Manuell einlagern“ verwenden.');state.item=d.item;state.itemCode=c;render()}catch(e){status(e.message,false)}});else{bindScan('binCode',async c=>{try{const qty=Math.max(1,parseInt($('#qty').value,10)||1);const d=await api('/inventory/putaway',{method:'POST',body:JSON.stringify({item_barcode:state.itemCode,bin_barcode:c,quantity:qty,user_label:'mobile'})});state={};render();status(`${qty} Stück eingelagert: ${d.bin.warehouse_name} / ${d.bin.rack_name} / ${d.bin.name}`,true)}catch(e){status(e.message,false)}});$('#reset').onclick=()=>{state={};render()}}}
function manualHtml(){if(!state.item)return '<div class="info warning"><b>Manuelle Einlagerung</b><div class="small">Diese Funktion erhöht den physischen Bestand direkt. Verwenden, wenn die Ware vorher nicht als Wareneingang am PC gebucht wurde.</div></div>'+scanField('itemCode','1. Artikelbarcode scannen')+'<div id="status" class="status"></div>';return `<div class="info warning"><b>${esc(itemText(state.item))}</b><div class="small">Aktueller Bestand ${state.item.physical_qty||0}. Die eingegebene Menge wird zusätzlich eingebucht und sofort dem gescannten Fach zugeordnet.</div></div><label class="small">Menge</label><input class="qty" id="qty" type="number" min="1" value="1">${scanField('binCode','2. Lagerfach scannen')}<div id="status" class="status"></div><button class="btn" id="reset">Anderen Artikel</button>`}
function bindManual(){if(!state.item)bindScan('itemCode',async c=>{try{const d=await resolve(c);if(d.type!=='stock_item')throw new Error('Bitte Artikelbarcode scannen.');state.item=d.item;state.itemCode=c;render()}catch(e){status(e.message,false)}});else{bindScan('binCode',async c=>{try{const qty=Math.max(1,parseInt($('#qty').value,10)||1);const d=await api('/inventory/manual-putaway',{method:'POST',body:JSON.stringify({item_barcode:state.itemCode,bin_barcode:c,quantity:qty,user_label:'mobile'})});state={};render();status(`${qty} Stück neu eingebucht und eingelagert: ${d.bin.warehouse_name} / ${d.bin.rack_name} / ${d.bin.name}`,true)}catch(e){status(e.message,false)}});$('#reset').onclick=()=>{state={};render()}}}
function relocateHtml(){if(!state.item)return scanField('itemCode','1. Artikelbarcode scannen')+'<div id="status" class="status"></div>';if(!state.source)return `<div class="info"><b>${esc(itemText(state.item))}</b></div>${scanField('sourceCode','2. Quellfach scannen')}<div id="status" class="status"></div>`;return `<div class="info"><b>${esc(itemText(state.item))}</b><div class="small">Quelle: ${esc(state.source.warehouse_name+' / '+state.source.rack_name+' / '+state.source.name)}</div></div><label class="small">Menge</label><input class="qty" id="qty" type="number" min="1" value="1">${scanField('targetCode','3. Zielfach scannen')}<div id="status" class="status"></div><button class="btn" id="reset">Neu beginnen</button>`}
function bindRelocate(){if(!state.item)bindScan('itemCode',async c=>{try{const d=await resolve(c);if(d.type!=='stock_item')throw new Error('Bitte Artikelbarcode scannen.');state.item=d.item;state.itemCode=c;render()}catch(e){status(e.message,false)}});else if(!state.source)bindScan('sourceCode',async c=>{try{const d=await resolve(c);if(d.type!=='bin')throw new Error('Bitte Fachbarcode scannen.');state.source=d.bin;state.sourceCode=c;render()}catch(e){status(e.message,false)}});else{bindScan('targetCode',async c=>{try{const qty=Math.max(1,parseInt($('#qty').value,10)||1);await api('/inventory/relocate',{method:'POST',body:JSON.stringify({item_barcode:state.itemCode,source_bin_barcode:state.sourceCode,target_bin_barcode:c,quantity:qty,user_label:'mobile'})});state={};render();status(`${qty} Stück umgelagert.`,true)}catch(e){status(e.message,false)}});$('#reset').onclick=()=>{state={};render()}}}
function checkHtml(){return scanField('checkCode','Artikel- oder Fachbarcode scannen')+'<div id="result"></div><div id="status" class="status"></div>'}
function bindCheck(){bindScan('checkCode',async c=>{try{const d=await resolve(c);if(d.type==='stock_item'){const x=d.item;$('#result').innerHTML=`<div class="info"><b>${esc(itemText(x))}</b><div class="small">Gesamt: ${x.physical_qty||0} · reserviert ${x.reserved_qty||0} · bestellt ${x.on_order_qty||0} · ohne Fach ${x.unassigned_qty||0}</div><div class="contentList">${(x.bins||[]).map(b=>`<div class="contentItem"><span>${esc(b.warehouse_name+' / '+b.rack_name+' / '+b.bin_name)}</span><b>${b.quantity}</b></div>`).join('')}</div></div>`}else{const b=d.bin;$('#result').innerHTML=`<div class="info"><b>${esc(b.warehouse_name+' / '+b.rack_name+' / '+b.name)}</b><div class="small">${esc(b.barcode)}</div><div class="contentList">${(b.contents||[]).map(x=>`<div class="contentItem"><span>${esc(itemText(x))}</span><b>${x.bin_qty}</b></div>`).join('')||'<div class="small">Fach ist leer.</div>'}</div></div>`}status('Gefunden.',true)}catch(e){status(e.message,false)}})}
function cameraMessage(text,kind=''){const el=$('#cameraStatus');if(!el)return;el.textContent=text;el.className='camera-status'+(kind?' '+kind:'')}
let quaggaLoadPromise=null;function loadQuagga(){if(window.Quagga)return Promise.resolve(window.Quagga);if(quaggaLoadPromise)return quaggaLoadPromise;quaggaLoadPromise=new Promise((resolve,reject)=>{const sources=['https://cdn.jsdelivr.net/npm/@ericblade/quagga2@1.11.0/dist/quagga.min.js','https://unpkg.com/@ericblade/quagga2@1.11.0/dist/quagga.min.js'];let i=0;const next=()=>{if(i>=sources.length){reject(new Error('iPhone-Barcodescanner konnte nicht geladen werden.'));return}const s=document.createElement('script');s.src=sources[i++];s.async=true;s.onload=()=>window.Quagga?resolve(window.Quagga):next();s.onerror=next;document.head.appendChild(s)};next()});return quaggaLoadPromise}
async function startQuaggaScanner(){const Q=await loadQuagga();cameraMessage('iPhone-Scanner wird gestartet …');await new Promise((resolve,reject)=>Q.init({inputStream:{type:'LiveStream',target:document.querySelector('#cameraWrap'),constraints:{facingMode:'environment',width:{min:1280,ideal:1920},height:{min:720,ideal:1080},aspectRatio:{min:1,max:2}}},locator:{patchSize:'medium',halfSample:true},numOfWorkers:2,frequency:12,decoder:{readers:['code_128_reader','code_39_reader','ean_reader','ean_8_reader']}},err=>err?reject(err):resolve()));Q.offDetected&&Q.offDetected();Q.onDetected(r=>{const code=r?.codeResult?.code;if(code)onBarcode(code)});Q.start();cameraMessage('Barcode vollständig in den orangefarbenen Rahmen halten. Langsam Abstand verändern.')}
function loadZXing(){if(window.ZXingBrowser)return Promise.resolve(window.ZXingBrowser);if(zxingLoadPromise)return zxingLoadPromise;zxingLoadPromise=new Promise((resolve,reject)=>{const sources=['https://cdn.jsdelivr.net/npm/@zxing/browser@0.2.1/umd/zxing-browser.min.js','https://unpkg.com/@zxing/browser@0.2.1/umd/zxing-browser.min.js'];let i=0;const next=()=>{if(i>=sources.length){reject(new Error('Barcode-Scanner konnte nicht geladen werden. Bitte Internetverbindung prüfen.'));return}const sc=document.createElement('script');sc.src=sources[i++];sc.async=true;sc.onload=()=>window.ZXingBrowser?resolve(window.ZXingBrowser):next();sc.onerror=()=>next();document.head.appendChild(sc)};next()});return zxingLoadPromise}
function onBarcode(text){text=String(text||'').trim();if(!text||text===lastDetected)return;lastDetected=text;cameraMessage('Erkannt: '+text,'good');if(navigator.vibrate)try{navigator.vibrate(80)}catch{}const cb=scanCallback;setTimeout(()=>{stopCamera();if(cb)cb(text)},180)}
async function enhanceTrack(video){try{const track=video?.srcObject?.getVideoTracks?.()[0];if(!track)return;const caps=track.getCapabilities?.()||{};const advanced={};if(Array.isArray(caps.focusMode)&&caps.focusMode.includes('continuous'))advanced.focusMode='continuous';if(Object.keys(advanced).length)await track.applyConstraints({advanced:[advanced]})}catch{}}
async function startNativeBarcodeDetector(){detector=new BarcodeDetector({formats:['code_128','code_39','ean_13','ean_8','qr_code']});stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}}});const video=$('#camera');video.srcObject=stream;video.muted=true;video.setAttribute('playsinline','');video.setAttribute('webkit-playsinline','');await video.play();await enhanceTrack(video);cameraMessage('Barcode waagerecht in den Rahmen halten.');tick()}
async function startZXingScanner(){const ZX=await loadZXing();zxingReader=new ZX.BrowserMultiFormatReader();const video=$('#camera');video.muted=true;video.setAttribute('playsinline','');video.setAttribute('webkit-playsinline','');cameraMessage('Kamera wird gestartet …');const constraints={audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}}};zxingControls=await zxingReader.decodeFromConstraints(constraints,video,(result,error)=>{if(result){let text='';try{text=result.getText?result.getText():(result.text||'')}catch{}if(text)onBarcode(text)}});await enhanceTrack(video);cameraMessage('Barcode vollständig und waagerecht in den Rahmen halten. Abstand langsam verändern.');scanHintTimer=setTimeout(()=>cameraMessage('Noch nicht erkannt: etwas weiter weg gehen, ruhig halten und auf gute Beleuchtung achten.','warn'),7000)}
function isIOS(){return /iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1)}
async function startCamera(cb){scanCallback=cb;lastDetected='';if(!window.isSecureContext){alert('Kamera-Scanning benötigt HTTPS.');return}if(!navigator.mediaDevices?.getUserMedia){alert('Dieser Browser erlaubt keinen Kamerazugriff.');return}$('#cameraWrap').classList.remove('hidden');cameraMessage('Kamera wird gestartet …');try{if(isIOS()){await startQuaggaScanner()}else if('BarcodeDetector'in window){await startNativeBarcodeDetector()}else{await startZXingScanner()}}catch(e){stopCamera();alert('Kamera konnte nicht gestartet werden: '+(e?.message||e))}}
async function tick(){if(!stream)return;try{const codes=await detector.detect($('#camera'));if(codes&&codes[0]?.rawValue){onBarcode(codes[0].rawValue);return}}catch{}raf=requestAnimationFrame(tick)}
function stopCamera(){try{if(window.Quagga)window.Quagga.stop()}catch{}clearTimeout(scanHintTimer);scanHintTimer=0;cancelAnimationFrame(raf);raf=0;if(zxingControls){try{zxingControls.stop()}catch{}zxingControls=null}if(zxingReader&&typeof zxingReader.reset==='function'){try{zxingReader.reset()}catch{}}if(stream){try{stream.getTracks().forEach(t=>t.stop())}catch{}stream=null}const video=$('#camera');if(video?.srcObject){try{video.srcObject.getTracks().forEach(t=>t.stop())}catch{}video.srcObject=null}$('#cameraWrap').classList.add('hidden');detector=null;scanCallback=null;lastDetected=''}
$('#cameraCancel').onclick=stopCamera;
if('serviceWorker'in navigator)navigator.serviceWorker.register('/api/hca-shared/mobile/sw.js').catch(()=>{});
</script>
</body></html>'''


@router.get("/mobile", response_class=HTMLResponse)
async def inventory_mobile_page() -> HTMLResponse:
    return HTMLResponse(MOBILE_HTML, headers={"Cache-Control":"no-store"})


@router.get("/mobile/manifest.webmanifest")
async def inventory_mobile_manifest() -> Response:
    data={"name":"HCA Lager","short_name":"HCA Lager","start_url":"/api/hca-shared/mobile","scope":"/api/hca-shared/mobile","display":"standalone","background_color":"#f4f4f2","theme_color":"#1d1d1b","icons":[]}
    return Response(_json(data), media_type="application/manifest+json")


@router.get("/mobile/sw.js")
async def inventory_mobile_sw() -> Response:
    js="self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));self.addEventListener('fetch',()=>{});"
    return Response(js, media_type="application/javascript", headers={"Cache-Control":"no-store"})





# ---------------------------------------------------------------------------
# HCA Business / CRM / Vertrieb (v0.10.0)
# Kaufmaennische Auftraege sind bewusst getrennt von Produktionsauftraegen.
# ---------------------------------------------------------------------------

BUSINESS_QUOTE_STATUSES = {"draft", "ready", "sent", "accepted", "rejected", "expired"}
BUSINESS_ORDER_STATUSES = {"draft", "confirmed", "in_progress", "partially_delivered", "delivered", "completed", "cancelled"}


def _business_next_no(conn: sqlite3.Connection, doc_type: str, prefix: str) -> str:
    year = datetime.now(timezone.utc).year
    row = conn.execute("SELECT year,last_no FROM business_sequences WHERE doc_type=?", (doc_type,)).fetchone()
    if not row or int(row["year"] or 0) != year:
        last_no = 1
        conn.execute(
            "INSERT INTO business_sequences(doc_type,year,last_no,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(doc_type) DO UPDATE SET year=excluded.year,last_no=excluded.last_no,updated_at=excluded.updated_at",
            (doc_type, year, last_no, _now()),
        )
    else:
        last_no = int(row["last_no"] or 0) + 1
        conn.execute("UPDATE business_sequences SET last_no=?,updated_at=? WHERE doc_type=?", (last_no, _now(), doc_type))
    return f"{prefix}-{year}-{last_no:04d}"


def _business_customer_name(row: sqlite3.Row | dict[str, Any] | None) -> str:
    if not row:
        return ""
    get = row.__getitem__ if isinstance(row, sqlite3.Row) else row.get
    company = str(get("company_name") or "").strip()
    person = " ".join(x for x in [str(get("first_name") or "").strip(), str(get("last_name") or "").strip()] if x)
    return company or person or str(get("customer_no") or "").strip()


def _business_customer_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["display_name"] = _business_customer_name(row)
    d["active"] = bool(d.get("active"))
    d["is_default"] = bool(d.get("is_default"))
    d["discount_pct"] = float(d.get("discount_pct") or 0)
    d["credit_balance"] = float(d.get("credit_balance") or 0)
    d["vouchers"] = str(d.get("vouchers") or "")
    return d


def _business_contact_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["display_name"] = " ".join(x for x in [str(d.get("first_name") or "").strip(), str(d.get("last_name") or "").strip()] if x) or str(d.get("email") or "")
    d["is_primary"] = bool(d.get("is_primary"))
    d["active"] = bool(d.get("active"))
    return d


def _business_address_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["is_default_billing"] = bool(d.get("is_default_billing"))
    d["is_default_shipping"] = bool(d.get("is_default_shipping"))
    d["active"] = bool(d.get("active"))
    return d


def _business_line_amounts(row: sqlite3.Row | dict[str, Any]) -> tuple[float, float, float]:
    d = dict(row)
    qty = float(d.get("quantity") or 0)
    unit_price = float(d.get("unit_price") or 0)
    discount = max(0.0, min(100.0, float(d.get("discount_pct") or 0)))
    tax = max(0.0, float(d.get("tax_rate") or 0))
    config = d.get("config") if isinstance(d.get("config"), dict) else _loads(d.get("config_json"), {})
    if not isinstance(config, dict):
        config = {}
    steps = config.get("production_steps") if isinstance(config.get("production_steps"), list) else []
    refinement_unit = 0.0
    setup_total = 0.0
    for step in steps:
        if not isinstance(step, dict):
            continue
        try:
            refinement_unit += max(0.0, float(step.get("unit_price") or 0))
        except Exception:
            pass
        try:
            setup_total += max(0.0, float(step.get("setup_price") or 0))
        except Exception:
            pass
    # Rabatt gilt für die mengenabhängigen Positionen; einmalige Einrichtungskosten bleiben separat.
    net = qty * (unit_price + refinement_unit) * (1.0 - discount / 100.0) + setup_total
    tax_value = net * tax / 100.0
    return round(net, 2), round(tax_value, 2), round(net + tax_value, 2)


def _business_line_total(row: sqlite3.Row | dict[str, Any]) -> tuple[float, float, float]:
    """Totals that contribute to the document total (options and text do not)."""
    item_type = str(dict(row).get("item_type") or "product").strip().lower()
    if item_type in {"optional", "text"}:
        return 0.0, 0.0, 0.0
    return _business_line_amounts(row)


def _business_item_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["config"] = _loads(d.pop("config_json", "{}"), {})
    net, tax, gross = (0.0, 0.0, 0.0) if str(d.get("item_type") or "product").lower() == "text" else _business_line_amounts(d)
    d.update({"net_total": net, "tax_total": tax, "gross_total": gross})
    return d


def _business_totals(rows: list[sqlite3.Row]) -> dict[str, float]:
    net = tax = gross = 0.0
    for row in rows:
        n, t, g = _business_line_total(row)
        net += n; tax += t; gross += g
    return {"net": round(net, 2), "tax": round(tax, 2), "gross": round(gross, 2)}


def _business_address_snapshot(customer: sqlite3.Row, address: sqlite3.Row | None, contact: sqlite3.Row | None = None) -> dict[str, Any]:
    person = " ".join(x for x in [str(contact["first_name"] or "").strip(), str(contact["last_name"] or "").strip()] if x) if contact else ""
    return {
        "name": str((address["company_name"] if address else "") or _business_customer_name(customer)),
        "attention": str((address["attention"] if address else "") or person),
        "street": str(address["street"] or "") if address else "",
        "zip": str(address["zip"] or "") if address else "",
        "city": str(address["city"] or "") if address else "",
        "country": str(address["country"] or "DE") if address else "DE",
        "email": str((contact["email"] if contact else "") or customer["email"] or ""),
        "phone": str((contact["phone"] if contact else "") or customer["phone"] or ""),
    }


def _business_customer_snapshot(conn: sqlite3.Connection, customer: sqlite3.Row, contact_id: str = "", billing_address_id: str = "", shipping_address_id: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    contact = conn.execute("SELECT * FROM crm_contacts WHERE id=? AND customer_id=? AND active=1", (contact_id, customer["id"])).fetchone() if contact_id else None
    bill_id = billing_address_id or (str(contact["default_billing_address_id"] or "") if contact else "") or str(customer["default_billing_address_id"] or "")
    ship_id = shipping_address_id or (str(contact["default_shipping_address_id"] or "") if contact else "") or str(customer["default_shipping_address_id"] or "")
    billing = conn.execute("SELECT * FROM crm_addresses WHERE id=? AND customer_id=? AND active=1", (bill_id, customer["id"])).fetchone() if bill_id else None
    shipping = conn.execute("SELECT * FROM crm_addresses WHERE id=? AND customer_id=? AND active=1", (ship_id, customer["id"])).fetchone() if ship_id else None
    if not billing:
        billing = conn.execute("SELECT * FROM crm_addresses WHERE customer_id=? AND active=1 ORDER BY is_default_billing DESC,created_at LIMIT 1", (customer["id"],)).fetchone()
    if not shipping:
        shipping = conn.execute("SELECT * FROM crm_addresses WHERE customer_id=? AND active=1 ORDER BY is_default_shipping DESC,created_at LIMIT 1", (customer["id"],)).fetchone()
    # Legacy fallback for customers without an address-book entry.
    if not billing:
        b={"company_name":_business_customer_name(customer),"attention":"","street":customer["billing_street"],"zip":customer["billing_zip"],"city":customer["billing_city"],"country":customer["billing_country"] or "DE"}
        billing=b
    if not shipping:
        sh={"company_name":_business_customer_name(customer),"attention":"","street":customer["shipping_street"] or customer["billing_street"],"zip":customer["shipping_zip"] or customer["billing_zip"],"city":customer["shipping_city"] or customer["billing_city"],"country":customer["shipping_country"] or customer["billing_country"] or "DE"}
        shipping=sh
    def snap(a):
        person = " ".join(x for x in [str(contact["first_name"] or "").strip(), str(contact["last_name"] or "").strip()] if x) if contact else ""
        get = a.__getitem__ if isinstance(a, sqlite3.Row) else a.get
        return {"name":str(get("company_name") or _business_customer_name(customer)),"attention":str(get("attention") or person),"street":str(get("street") or ""),"zip":str(get("zip") or ""),"city":str(get("city") or ""),"country":str(get("country") or "DE"),"email":str((contact["email"] if contact else "") or customer["email"] or ""),"phone":str((contact["phone"] if contact else "") or customer["phone"] or "")}
    return snap(billing), snap(shipping)


def _business_replace_items(conn: sqlite3.Connection, table: str, parent_col: str, parent_id: str, items: list[dict[str, Any]]) -> None:
    if table not in {"sales_quote_items", "sales_order_items"}:
        raise ValueError("Unbekannte Positionstabelle")
    conn.execute(f"DELETE FROM {table} WHERE {parent_col}=?", (parent_id,))
    now = _now()
    pos = 10
    for raw in items or []:
        item = raw if isinstance(raw, dict) else {}
        desc = str(item.get("description") or item.get("article") or "").strip()
        if not desc:
            continue
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        qty = float(item.get("quantity") or 0)
        sizes = config.get("sizes") if isinstance(config.get("sizes"), dict) else {}
        if sizes:
            qty = sum(max(0.0, float(v or 0)) for v in sizes.values())
        if qty <= 0:
            qty = 1.0
        conn.execute(
            f"INSERT INTO {table}(id,{parent_col},position_no,item_type,product_id,sku,description,quantity,unit,unit_price,discount_pct,tax_rate,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), parent_id, int(item.get("position_no") or pos), str(item.get("item_type") or "product"),
                str(item.get("product_id") or ""), str(item.get("sku") or ""), desc, qty, str(item.get("unit") or "Stk."),
                float(item.get("unit_price") or 0), float(item.get("discount_pct") or 0), float(item.get("tax_rate") if item.get("tax_rate") is not None else 19),
                _json(config), now, now,
            ),
        )
        pos += 10


def _business_quote_dict(conn: sqlite3.Connection, row: sqlite3.Row, include_items: bool = True) -> dict[str, Any]:
    d = dict(row)
    items = conn.execute("SELECT * FROM sales_quote_items WHERE quote_id=? ORDER BY position_no,id", (row["id"],)).fetchall()
    d["totals"] = _business_totals(items)
    d["item_count"] = len(items)
    if include_items:
        d["items"] = [_business_item_dict(x) for x in items]
    return d


def _business_order_dict(conn: sqlite3.Connection, row: sqlite3.Row, include_items: bool = True) -> dict[str, Any]:
    d = dict(row)
    d["billing"] = _loads(d.pop("billing_json", "{}"), {})
    d["shipping"] = _loads(d.pop("shipping_json", "{}"), {})
    items = conn.execute("SELECT * FROM sales_order_items WHERE sales_order_id=? ORDER BY position_no,id", (row["id"],)).fetchall()
    d["totals"] = _business_totals(items)
    d["item_count"] = len(items)
    d["production_order_count"] = int(conn.execute("SELECT COUNT(*) FROM production_order_links WHERE sales_order_id=?", (row["id"],)).fetchone()[0])
    if include_items:
        d["items"] = [_business_item_dict(x) for x in items]
    return d


def _business_sync_customer_default_addresses(conn: sqlite3.Connection, customer_id: str, values: dict[str, Any]) -> None:
    customer = conn.execute("SELECT * FROM crm_customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        return
    now=_now(); name=_business_customer_name(customer)
    bill_vals=(values.get("billing_street", ""), values.get("billing_zip", ""), values.get("billing_city", ""), values.get("billing_country", "DE") or "DE")
    ship_vals=(values.get("shipping_street", ""), values.get("shipping_zip", ""), values.get("shipping_city", ""), values.get("shipping_country", values.get("billing_country", "DE")) or "DE")
    bill_id=str(customer["default_billing_address_id"] or "")
    ship_id=str(customer["default_shipping_address_id"] or "")
    if any(str(x or "").strip() for x in bill_vals[:3]):
        if bill_id and conn.execute("SELECT 1 FROM crm_addresses WHERE id=? AND customer_id=?",(bill_id,customer_id)).fetchone():
            conn.execute("UPDATE crm_addresses SET company_name=?,street=?,zip=?,city=?,country=?,is_default_billing=1,active=1,updated_at=? WHERE id=?",(name,*bill_vals,now,bill_id))
        else:
            bill_id=str(uuid.uuid4())
            conn.execute("UPDATE crm_addresses SET is_default_billing=0,updated_at=? WHERE customer_id=?",(now,customer_id))
            conn.execute("INSERT INTO crm_addresses(id,customer_id,label,company_name,attention,street,zip,city,country,is_default_billing,is_default_shipping,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(bill_id,customer_id,"Rechnungsadresse",name,"",*bill_vals,1,0,1,now,now))
            conn.execute("UPDATE crm_customers SET default_billing_address_id=? WHERE id=?",(bill_id,customer_id))
    if any(str(x or "").strip() for x in ship_vals[:3]):
        if ship_id and conn.execute("SELECT 1 FROM crm_addresses WHERE id=? AND customer_id=?",(ship_id,customer_id)).fetchone():
            conn.execute("UPDATE crm_addresses SET company_name=?,street=?,zip=?,city=?,country=?,is_default_shipping=1,active=1,updated_at=? WHERE id=?",(name,*ship_vals,now,ship_id))
        else:
            # Reuse billing address if both addresses are identical.
            if bill_id and tuple(str(x or "").strip() for x in ship_vals)==tuple(str(x or "").strip() for x in bill_vals):
                ship_id=bill_id
                conn.execute("UPDATE crm_addresses SET is_default_shipping=1,updated_at=? WHERE id=?",(now,ship_id))
            else:
                ship_id=str(uuid.uuid4())
                conn.execute("UPDATE crm_addresses SET is_default_shipping=0,updated_at=? WHERE customer_id=?",(now,customer_id))
                conn.execute("INSERT INTO crm_addresses(id,customer_id,label,company_name,attention,street,zip,city,country,is_default_billing,is_default_shipping,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ship_id,customer_id,"Lieferadresse",name,"",*ship_vals,0,1,1,now,now))
            conn.execute("UPDATE crm_customers SET default_shipping_address_id=? WHERE id=?",(ship_id,customer_id))


def _business_customer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "customer_type","company_name","salutation","first_name","last_name","email","phone","mobile","website","vat_id","tax_no",
        "billing_street","billing_zip","billing_city","billing_country","shipping_street","shipping_zip","shipping_city","shipping_country","notes"
    ]
    out = {k: str(payload.get(k) or "").strip() for k in fields}
    out["customer_type"] = out["customer_type"] or "customer"
    out["billing_country"] = out["billing_country"] or "DE"
    out["shipping_country"] = out["shipping_country"] or out["billing_country"] or "DE"
    out["active"] = 1 if payload.get("active", True) else 0
    out["is_default"] = 1 if payload.get("is_default") else 0
    out["discount_pct"] = max(0.0, min(100.0, float(payload.get("discount_pct") or 0)))
    out["credit_balance"] = float(payload.get("credit_balance") or 0)
    vouchers = payload.get("vouchers")
    out["vouchers"] = "\n".join(str(x).strip() for x in vouchers if str(x).strip()) if isinstance(vouchers,list) else str(vouchers or "").strip()
    if not (out["company_name"] or out["last_name"] or out["first_name"]):
        raise HTTPException(status_code=400, detail="Bitte Firmenname oder Ansprechpartner angeben.")
    return out


@router.get("/business/dashboard", dependencies=auth)
async def business_dashboard() -> dict[str, Any]:
    with _db() as conn:
        result = {
            "customers": int(conn.execute("SELECT COUNT(*) FROM crm_customers WHERE active=1").fetchone()[0]),
            "quotes_open": int(conn.execute("SELECT COUNT(*) FROM sales_quotes WHERE status IN ('draft','ready','sent')").fetchone()[0]),
            "quotes_sent": int(conn.execute("SELECT COUNT(*) FROM sales_quotes WHERE status='sent'").fetchone()[0]),
            "orders_open": int(conn.execute("SELECT COUNT(*) FROM sales_orders WHERE status NOT IN ('completed','cancelled')").fetchone()[0]),
            "production_orders_open": int(conn.execute("SELECT COUNT(*) FROM production_order_links WHERE status NOT IN ('completed','cancelled')").fetchone()[0]),
            "invoices_open": int(conn.execute("SELECT COUNT(*) FROM finance_invoices WHERE status NOT IN ('paid','voided','cancelled')").fetchone()[0]),
        }
        recent_quotes = conn.execute("SELECT * FROM sales_quotes ORDER BY updated_at DESC LIMIT 5").fetchall()
        recent_orders = conn.execute("SELECT * FROM sales_orders ORDER BY updated_at DESC LIMIT 5").fetchall()
        result["recent_quotes"] = [_business_quote_dict(conn, r, False) for r in recent_quotes]
        result["recent_orders"] = [_business_order_dict(conn, r, False) for r in recent_orders]
        return {"ok": True, **result}


@router.get("/crm/customers", dependencies=auth)
async def crm_customers(q: str = "", active: int = 1, limit: int = 500) -> dict[str, Any]:
    with _db() as conn:
        params: list[Any] = []
        where: list[str] = []
        if int(active) >= 0:
            where.append("active=?"); params.append(1 if int(active) else 0)
        if str(q or "").strip():
            like = f"%{str(q).strip()}%"
            where.append("(customer_no LIKE ? OR company_name LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR billing_city LIKE ?)")
            params.extend([like] * 6)
        sql = "SELECT * FROM crm_customers" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY is_default DESC,company_name,last_name,first_name LIMIT ?"
        params.append(max(1, min(int(limit or 500), 2000)))
        rows = conn.execute(sql, params).fetchall()
        items = []
        for row in rows:
            d = _business_customer_dict(row)
            d["quotes"] = int(conn.execute("SELECT COUNT(*) FROM sales_quotes WHERE customer_id=?", (row["id"],)).fetchone()[0])
            d["orders"] = int(conn.execute("SELECT COUNT(*) FROM sales_orders WHERE customer_id=?", (row["id"],)).fetchone()[0])
            items.append(d)
        return {"ok": True, "items": items}


@router.post("/crm/customers", dependencies=auth)
async def crm_customer_create(request: Request) -> dict[str, Any]:
    payload = await request.json()
    values = _business_customer_payload(payload if isinstance(payload, dict) else {})
    now = _now(); cid = str(uuid.uuid4())
    with _db() as conn:
        no = str(payload.get("customer_no") or "").strip() if isinstance(payload, dict) else ""
        if not no:
            no = _business_next_no(conn, "customer", "KD")
        if values["is_default"]:
            conn.execute("UPDATE crm_customers SET is_default=0,updated_at=?", (now,))
        conn.execute(
            "INSERT INTO crm_customers(id,customer_no,customer_type,company_name,salutation,first_name,last_name,email,phone,mobile,website,vat_id,tax_no,billing_street,billing_zip,billing_city,billing_country,shipping_street,shipping_zip,shipping_city,shipping_country,notes,active,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid,no,values["customer_type"],values["company_name"],values["salutation"],values["first_name"],values["last_name"],values["email"],values["phone"],values["mobile"],values["website"],values["vat_id"],values["tax_no"],values["billing_street"],values["billing_zip"],values["billing_city"],values["billing_country"],values["shipping_street"],values["shipping_zip"],values["shipping_city"],values["shipping_country"],values["notes"],values["active"],values["is_default"],now,now),
        )
        _business_sync_customer_default_addresses(conn,cid,values)
        conn.execute("UPDATE crm_customers SET discount_pct=?,credit_balance=?,vouchers=? WHERE id=?", (values["discount_pct"],values["credit_balance"],values["vouchers"],cid))
        row = conn.execute("SELECT * FROM crm_customers WHERE id=?", (cid,)).fetchone()
        return {"ok": True, "item": _business_customer_dict(row)}


@router.get("/crm/customers/{customer_id}", dependencies=auth)
async def crm_customer_get(customer_id: str) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM crm_customers WHERE id=?", (customer_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden.")
        item = _business_customer_dict(row)
        item["contacts"] = [_business_contact_dict(x) for x in conn.execute("SELECT * FROM crm_contacts WHERE customer_id=? AND active=1 ORDER BY is_primary DESC,last_name,first_name", (customer_id,)).fetchall()]
        item["addresses"] = [_business_address_dict(x) for x in conn.execute("SELECT * FROM crm_addresses WHERE customer_id=? AND active=1 ORDER BY is_default_billing DESC,is_default_shipping DESC,label,created_at", (customer_id,)).fetchall()]
        item["quotes"] = [_business_quote_dict(conn, x, False) for x in conn.execute("SELECT * FROM sales_quotes WHERE customer_id=? ORDER BY updated_at DESC LIMIT 50", (customer_id,)).fetchall()]
        item["orders"] = [_business_order_dict(conn, x, False) for x in conn.execute("SELECT * FROM sales_orders WHERE customer_id=? ORDER BY updated_at DESC LIMIT 50", (customer_id,)).fetchall()]
        item["invoices"] = [_finance_invoice_dict(conn, x, False) for x in conn.execute("SELECT * FROM finance_invoices WHERE customer_id=? AND direction='customer' ORDER BY invoice_date DESC,updated_at DESC LIMIT 50", (customer_id,)).fetchall()]
        return {"ok": True, "item": item}


@router.put("/crm/customers/{customer_id}", dependencies=auth)
async def crm_customer_update(customer_id: str, request: Request) -> dict[str, Any]:
    payload = await request.json(); values = _business_customer_payload(payload if isinstance(payload, dict) else {})
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM crm_customers WHERE id=?", (customer_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden.")
        if values["is_default"]:
            conn.execute("UPDATE crm_customers SET is_default=0,updated_at=? WHERE id<>?", (_now(),customer_id))
        conn.execute(
            "UPDATE crm_customers SET customer_type=?,company_name=?,salutation=?,first_name=?,last_name=?,email=?,phone=?,mobile=?,website=?,vat_id=?,tax_no=?,billing_street=?,billing_zip=?,billing_city=?,billing_country=?,shipping_street=?,shipping_zip=?,shipping_city=?,shipping_country=?,notes=?,active=?,is_default=?,updated_at=? WHERE id=?",
            (values["customer_type"],values["company_name"],values["salutation"],values["first_name"],values["last_name"],values["email"],values["phone"],values["mobile"],values["website"],values["vat_id"],values["tax_no"],values["billing_street"],values["billing_zip"],values["billing_city"],values["billing_country"],values["shipping_street"],values["shipping_zip"],values["shipping_city"],values["shipping_country"],values["notes"],values["active"],values["is_default"],_now(),customer_id),
        )
        _business_sync_customer_default_addresses(conn,customer_id,values)
        conn.execute("UPDATE crm_customers SET discount_pct=?,credit_balance=?,vouchers=? WHERE id=?", (values["discount_pct"],values["credit_balance"],values["vouchers"],customer_id))
        return {"ok": True, "item": _business_customer_dict(conn.execute("SELECT * FROM crm_customers WHERE id=?", (customer_id,)).fetchone())}


@router.post("/crm/customers/{customer_id}/contacts", dependencies=auth)
async def crm_contact_create(customer_id: str, request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM crm_customers WHERE id=?", (customer_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden.")
        cid = str(uuid.uuid4()); now = _now(); primary = 1 if payload.get("is_primary") else 0
        if primary:
            conn.execute("UPDATE crm_contacts SET is_primary=0,updated_at=? WHERE customer_id=?", (now, customer_id))
        conn.execute(
            "INSERT INTO crm_contacts(id,customer_id,salutation,first_name,last_name,role,email,phone,mobile,is_primary,active,created_at,updated_at,default_billing_address_id,default_shipping_address_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid,customer_id,str(payload.get("salutation") or "").strip(),str(payload.get("first_name") or "").strip(),str(payload.get("last_name") or "").strip(),str(payload.get("role") or "").strip(),str(payload.get("email") or "").strip(),str(payload.get("phone") or "").strip(),str(payload.get("mobile") or "").strip(),primary,1,now,now,str(payload.get("default_billing_address_id") or ""),str(payload.get("default_shipping_address_id") or "")),
        )
        return {"ok": True, "item": _business_contact_dict(conn.execute("SELECT * FROM crm_contacts WHERE id=?", (cid,)).fetchone())}


@router.put("/crm/contacts/{contact_id}", dependencies=auth)
async def crm_contact_update(contact_id: str, request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}
    with _db() as conn:
        old = conn.execute("SELECT * FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
        if not old: raise HTTPException(status_code=404, detail="Kontakt nicht gefunden.")
        now=_now(); primary=1 if payload.get("is_primary") else 0
        if primary: conn.execute("UPDATE crm_contacts SET is_primary=0,updated_at=? WHERE customer_id=?", (now, old["customer_id"]))
        conn.execute("UPDATE crm_contacts SET salutation=?,first_name=?,last_name=?,role=?,email=?,phone=?,mobile=?,is_primary=?,active=?,updated_at=?,default_billing_address_id=?,default_shipping_address_id=? WHERE id=?", (
            str(payload.get("salutation") or "").strip(),str(payload.get("first_name") or "").strip(),str(payload.get("last_name") or "").strip(),str(payload.get("role") or "").strip(),str(payload.get("email") or "").strip(),str(payload.get("phone") or "").strip(),str(payload.get("mobile") or "").strip(),primary,1 if payload.get("active",True) else 0,now,str(payload.get("default_billing_address_id") or ""),str(payload.get("default_shipping_address_id") or ""),contact_id))
        return {"ok":True,"item":_business_contact_dict(conn.execute("SELECT * FROM crm_contacts WHERE id=?",(contact_id,)).fetchone())}


@router.post("/crm/customers/{customer_id}/addresses", dependencies=auth)
async def crm_address_create(customer_id: str, request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}
    with _db() as conn:
        customer = conn.execute("SELECT * FROM crm_customers WHERE id=?", (customer_id,)).fetchone()
        if not customer: raise HTTPException(status_code=404, detail="Kunde nicht gefunden.")
        aid=str(uuid.uuid4()); now=_now(); db=1 if payload.get("is_default_billing") else 0; ds=1 if payload.get("is_default_shipping") else 0
        if db: conn.execute("UPDATE crm_addresses SET is_default_billing=0,updated_at=? WHERE customer_id=?", (now,customer_id))
        if ds: conn.execute("UPDATE crm_addresses SET is_default_shipping=0,updated_at=? WHERE customer_id=?", (now,customer_id))
        conn.execute("INSERT INTO crm_addresses(id,customer_id,label,company_name,attention,street,zip,city,country,is_default_billing,is_default_shipping,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (aid,customer_id,str(payload.get("label") or "Adresse").strip(),str(payload.get("company_name") or _business_customer_name(customer)).strip(),str(payload.get("attention") or "").strip(),str(payload.get("street") or "").strip(),str(payload.get("zip") or "").strip(),str(payload.get("city") or "").strip(),str(payload.get("country") or "DE").strip() or "DE",db,ds,1,now,now))
        if db: conn.execute("UPDATE crm_customers SET default_billing_address_id=?,updated_at=? WHERE id=?", (aid,now,customer_id))
        if ds: conn.execute("UPDATE crm_customers SET default_shipping_address_id=?,updated_at=? WHERE id=?", (aid,now,customer_id))
        return {"ok":True,"item":_business_address_dict(conn.execute("SELECT * FROM crm_addresses WHERE id=?",(aid,)).fetchone())}


@router.put("/crm/addresses/{address_id}", dependencies=auth)
async def crm_address_update(address_id: str, request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}
    with _db() as conn:
        old=conn.execute("SELECT * FROM crm_addresses WHERE id=?",(address_id,)).fetchone()
        if not old: raise HTTPException(status_code=404, detail="Adresse nicht gefunden.")
        customer_id=old["customer_id"]; now=_now(); db=1 if payload.get("is_default_billing") else 0; ds=1 if payload.get("is_default_shipping") else 0
        if db: conn.execute("UPDATE crm_addresses SET is_default_billing=0,updated_at=? WHERE customer_id=?",(now,customer_id))
        if ds: conn.execute("UPDATE crm_addresses SET is_default_shipping=0,updated_at=? WHERE customer_id=?",(now,customer_id))
        conn.execute("UPDATE crm_addresses SET label=?,company_name=?,attention=?,street=?,zip=?,city=?,country=?,is_default_billing=?,is_default_shipping=?,active=?,updated_at=? WHERE id=?",(str(payload.get("label") or "Adresse").strip(),str(payload.get("company_name") or "").strip(),str(payload.get("attention") or "").strip(),str(payload.get("street") or "").strip(),str(payload.get("zip") or "").strip(),str(payload.get("city") or "").strip(),str(payload.get("country") or "DE").strip() or "DE",db,ds,1 if payload.get("active",True) else 0,now,address_id))
        if db: conn.execute("UPDATE crm_customers SET default_billing_address_id=?,updated_at=? WHERE id=?",(address_id,now,customer_id))
        if ds: conn.execute("UPDATE crm_customers SET default_shipping_address_id=?,updated_at=? WHERE id=?",(address_id,now,customer_id))
        return {"ok":True,"item":_business_address_dict(conn.execute("SELECT * FROM crm_addresses WHERE id=?",(address_id,)).fetchone())}


@router.get("/crm/default-customer", dependencies=auth)
async def crm_default_customer() -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM crm_customers WHERE active=1 AND is_default=1 ORDER BY updated_at DESC LIMIT 1").fetchone()
        return {"ok":True,"item":_business_customer_dict(row) if row else None}


@router.get("/sales/quotes", dependencies=auth)
async def sales_quotes(q: str = "", status: str = "", limit: int = 500) -> dict[str, Any]:
    with _db() as conn:
        where=[]; params=[]
        if status: where.append("status=?"); params.append(status)
        if str(q or "").strip():
            like=f"%{str(q).strip()}%"; where.append("(quote_no LIKE ? OR customer_name LIKE ? OR subject LIKE ?)"); params.extend([like,like,like])
        sql="SELECT * FROM sales_quotes"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY updated_at DESC LIMIT ?"; params.append(max(1,min(int(limit or 500),2000)))
        return {"ok":True,"items":[_business_quote_dict(conn,r,False) for r in conn.execute(sql,params).fetchall()]}


@router.post("/sales/quotes", dependencies=auth)
async def sales_quote_create(request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    customer_id=str(payload.get("customer_id") or "").strip()
    with _db() as conn:
        customer=conn.execute("SELECT * FROM crm_customers WHERE id=? AND active=1",(customer_id,)).fetchone()
        if not customer: raise HTTPException(status_code=400,detail="Bitte einen gültigen Kunden auswählen.")
        qid=str(uuid.uuid4()); qno=_business_next_no(conn,"quote","AN"); now=_now()
        conn.execute("INSERT INTO sales_quotes(id,quote_no,customer_id,customer_name,contact_id,subject,status,valid_until,currency,intro_text,footer_text,internal_note,sales_order_id,sent_at,accepted_at,created_at,updated_at,billing_address_id,shipping_address_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
            qid,qno,customer_id,_business_customer_name(customer),str(payload.get("contact_id") or ""),str(payload.get("subject") or "").strip(),"draft",str(payload.get("valid_until") or ""),str(payload.get("currency") or "EUR"),str(payload.get("intro_text") or ""),str(payload.get("footer_text") or ""),str(payload.get("internal_note") or ""),"","","",now,now,str(payload.get("billing_address_id") or ""),str(payload.get("shipping_address_id") or "")))
        _business_replace_items(conn,"sales_quote_items","quote_id",qid,payload.get("items") or [])
        return {"ok":True,"item":_business_quote_dict(conn,conn.execute("SELECT * FROM sales_quotes WHERE id=?",(qid,)).fetchone())}


@router.get("/sales/quotes/{quote_id}", dependencies=auth)
async def sales_quote_get(quote_id: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM sales_quotes WHERE id=?",(quote_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Angebot nicht gefunden.")
        return {"ok":True,"item":_business_quote_dict(conn,row)}


@router.put("/sales/quotes/{quote_id}", dependencies=auth)
async def sales_quote_update(quote_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    with _db() as conn:
        row=conn.execute("SELECT * FROM sales_quotes WHERE id=?",(quote_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Angebot nicht gefunden.")
        customer_id=str(payload.get("customer_id") or row["customer_id"])
        customer=conn.execute("SELECT * FROM crm_customers WHERE id=?",(customer_id,)).fetchone()
        if not customer: raise HTTPException(status_code=400,detail="Kunde nicht gefunden.")
        conn.execute("UPDATE sales_quotes SET customer_id=?,customer_name=?,contact_id=?,subject=?,valid_until=?,currency=?,intro_text=?,footer_text=?,internal_note=?,billing_address_id=?,shipping_address_id=?,updated_at=? WHERE id=?",(
            customer_id,_business_customer_name(customer),str(payload.get("contact_id") or ""),str(payload.get("subject") or "").strip(),str(payload.get("valid_until") or ""),str(payload.get("currency") or "EUR"),str(payload.get("intro_text") or ""),str(payload.get("footer_text") or ""),str(payload.get("internal_note") or ""),str(payload.get("billing_address_id") or ""),str(payload.get("shipping_address_id") or ""),_now(),quote_id))
        _business_replace_items(conn,"sales_quote_items","quote_id",quote_id,payload.get("items") or [])
        return {"ok":True,"item":_business_quote_dict(conn,conn.execute("SELECT * FROM sales_quotes WHERE id=?",(quote_id,)).fetchone())}


@router.post("/sales/quotes/{quote_id}/status", dependencies=auth)
async def sales_quote_status(quote_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); status=str((payload or {}).get("status") or "").strip().lower()
    if status not in BUSINESS_QUOTE_STATUSES: raise HTTPException(status_code=400,detail="Ungültiger Angebotsstatus.")
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM sales_quotes WHERE id=?",(quote_id,)).fetchone(): raise HTTPException(status_code=404,detail="Angebot nicht gefunden.")
        sent=_now() if status=="sent" else None; accepted=_now() if status=="accepted" else None
        if sent: conn.execute("UPDATE sales_quotes SET status=?,sent_at=?,updated_at=? WHERE id=?",(status,sent,_now(),quote_id))
        elif accepted: conn.execute("UPDATE sales_quotes SET status=?,accepted_at=?,updated_at=? WHERE id=?",(status,accepted,_now(),quote_id))
        else: conn.execute("UPDATE sales_quotes SET status=?,updated_at=? WHERE id=?",(status,_now(),quote_id))
        return {"ok":True,"item":_business_quote_dict(conn,conn.execute("SELECT * FROM sales_quotes WHERE id=?",(quote_id,)).fetchone())}


@router.post("/sales/quotes/{quote_id}/convert-to-order", dependencies=auth)
async def sales_quote_convert(quote_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    with _db() as conn:
        quote=conn.execute("SELECT * FROM sales_quotes WHERE id=?",(quote_id,)).fetchone()
        if not quote: raise HTTPException(status_code=404,detail="Angebot nicht gefunden.")
        if quote["sales_order_id"]:
            existing=conn.execute("SELECT * FROM sales_orders WHERE id=?",(quote["sales_order_id"],)).fetchone()
            if existing: return {"ok":True,"item":_business_order_dict(conn,existing),"already_exists":True}
        customer=conn.execute("SELECT * FROM crm_customers WHERE id=?",(quote["customer_id"],)).fetchone()
        if not customer: raise HTTPException(status_code=409,detail="Der Kunde zum Angebot existiert nicht mehr.")
        oid=str(uuid.uuid4()); ono=_business_next_no(conn,"sales_order","AU"); now=_now(); billing,shipping=_business_customer_snapshot(conn,customer,str(quote["contact_id"] or ""),str(quote["billing_address_id"] or ""),str(quote["shipping_address_id"] or ""))
        conn.execute("INSERT INTO sales_orders(id,order_no,source_quote_id,customer_id,customer_name,contact_id,subject,status,due_date,customer_reference,billing_json,shipping_json,internal_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
            oid,ono,quote_id,quote["customer_id"],quote["customer_name"],quote["contact_id"],quote["subject"],"confirmed",str(payload.get("due_date") or ""),str(payload.get("customer_reference") or ""),_json(billing),_json(shipping),str(payload.get("internal_note") or quote["internal_note"] or ""),now,now))
        conn.execute("UPDATE sales_orders SET payment_term_id=?,payment_term_text=? WHERE id=?",(str(quote["payment_term_id"] or ""),str(quote["payment_term_text"] or ""),oid))
        items=conn.execute("SELECT * FROM sales_quote_items WHERE quote_id=? ORDER BY position_no,id",(quote_id,)).fetchall()
        for r in items:
            if str(r["item_type"] or "product").lower() == "optional":
                continue
            conn.execute("INSERT INTO sales_order_items(id,sales_order_id,position_no,item_type,product_id,sku,description,quantity,unit,unit_price,discount_pct,tax_rate,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                str(uuid.uuid4()),oid,r["position_no"],r["item_type"],r["product_id"],r["sku"],r["description"],r["quantity"],r["unit"],r["unit_price"],r["discount_pct"],r["tax_rate"],r["config_json"],now,now))
        conn.execute("UPDATE sales_quotes SET status='accepted',sales_order_id=?,accepted_at=?,updated_at=? WHERE id=?",(oid,now,now,quote_id))
        return {"ok":True,"item":_business_order_dict(conn,conn.execute("SELECT * FROM sales_orders WHERE id=?",(oid,)).fetchone())}


@router.get("/sales/orders", dependencies=auth)
async def sales_orders(q: str = "", status: str = "", limit: int = 500) -> dict[str, Any]:
    with _db() as conn:
        where=[]; params=[]
        if status: where.append("status=?"); params.append(status)
        if str(q or "").strip():
            like=f"%{str(q).strip()}%"; where.append("(order_no LIKE ? OR customer_name LIKE ? OR subject LIKE ? OR customer_reference LIKE ?)"); params.extend([like]*4)
        sql="SELECT * FROM sales_orders"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY updated_at DESC LIMIT ?"; params.append(max(1,min(int(limit or 500),2000)))
        return {"ok":True,"items":[_business_order_dict(conn,r,False) for r in conn.execute(sql,params).fetchall()]}


@router.get("/sales/orders/{sales_order_id}", dependencies=auth)
async def sales_order_get(sales_order_id: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        return {"ok":True,"item":_business_order_dict(conn,row)}


@router.post("/sales/orders/{sales_order_id}/status", dependencies=auth)
async def sales_order_status(sales_order_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); status=str((payload or {}).get("status") or "").strip().lower()
    if status not in BUSINESS_ORDER_STATUSES: raise HTTPException(status_code=400,detail="Ungültiger Auftragsstatus.")
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone(): raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        conn.execute("UPDATE sales_orders SET status=?,updated_at=? WHERE id=?",(status,_now(),sales_order_id))
        return {"ok":True,"item":_business_order_dict(conn,conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone())}


def _business_material_rows(conn: sqlite3.Connection, sales_order_id: str) -> list[dict[str, Any]]:
    out=[]
    items=conn.execute("SELECT * FROM sales_order_items WHERE sales_order_id=? ORDER BY position_no,id",(sales_order_id,)).fetchall()
    for item in items:
        config=_loads(item["config_json"],{})
        if not isinstance(config,dict): config={}
        color=str(config.get("color") or "")
        sizes=config.get("sizes") if isinstance(config.get("sizes"),dict) else {}
        size_skus=config.get("size_skus") if isinstance(config.get("size_skus"),dict) else {}
        needs=[]
        if sizes:
            for size,qty in sizes.items():
                q=max(0,int(float(qty or 0)))
                if q: needs.append((str(size),q,str(size_skus.get(size) or item["sku"] or "")))
        else:
            q=max(1,int(float(item["quantity"] or 1))); needs.append((str(config.get("size") or ""),q,str(item["sku"] or "")))
        for size,qty,sku in needs:
            stock=None
            candidates=[]
            if sku:
                candidates=conn.execute("SELECT s.*,a.name AS article_name FROM inventory_stock_items s LEFT JOIN inventory_articles a ON a.id=s.article_id WHERE s.active=1 AND s.sku=? ORDER BY CASE WHEN s.color=? THEN 0 ELSE 1 END,CASE WHEN s.size=? THEN 0 ELSE 1 END LIMIT 20",(sku,color,size)).fetchall()
            if not candidates and item["product_id"]:
                candidates=conn.execute("SELECT s.*,a.name AS article_name FROM inventory_stock_items s LEFT JOIN inventory_articles a ON a.id=s.article_id WHERE s.active=1 AND s.woo_product_id=? ORDER BY CASE WHEN s.color=? THEN 0 ELSE 1 END,CASE WHEN s.size=? THEN 0 ELSE 1 END LIMIT 20",(str(item["product_id"]),color,size)).fetchall()
            for cand in candidates:
                if color and str(cand["color"] or "").lower()!=color.lower(): continue
                if size and str(cand["size"] or "").lower()!=size.lower(): continue
                stock=cand; break
            if not stock and candidates: stock=candidates[0]
            physical=int(stock["physical_qty"] or 0) if stock else 0; reserved=int(stock["reserved_qty"] or 0) if stock else 0; available=max(0,physical-reserved)
            out.append({"item_id":item["id"],"description":item["description"],"sku":sku,"color":color,"size":size,"required_qty":qty,"physical_qty":physical,"reserved_qty":reserved,"available_qty":available,"missing_qty":max(0,qty-available),"stock_item_id":stock["id"] if stock else "","barcode":stock["barcode"] if stock else ""})
    return out


@router.get("/sales/orders/{sales_order_id}/material", dependencies=auth)
async def sales_order_material(sales_order_id: str) -> dict[str, Any]:
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone(): raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        rows=_business_material_rows(conn,sales_order_id)
        return {"ok":True,"items":rows,"required_qty":sum(x["required_qty"] for x in rows),"missing_qty":sum(x["missing_qty"] for x in rows)}


def _business_production_groups(conn: sqlite3.Connection, sales_order_id: str, mode: str) -> dict[str,list[dict[str,Any]]]:
    groups: dict[str,list[dict[str,Any]]]={}
    items=conn.execute("SELECT * FROM sales_order_items WHERE sales_order_id=? ORDER BY position_no,id",(sales_order_id,)).fetchall()
    for item in items:
        config=_loads(item["config_json"],{})
        if not isinstance(config,dict): config={}
        color=str(config.get("color") or "")
        sizes=config.get("sizes") if isinstance(config.get("sizes"),dict) else {}
        size_skus=config.get("size_skus") if isinstance(config.get("size_skus"),dict) else {}
        if not sizes: sizes={str(config.get("size") or ""): max(1,int(float(item["quantity"] or 1)))}
        steps=config.get("production_steps") if isinstance(config.get("production_steps"),list) else []
        if not steps: steps=[{"technique":"none","position":"","motif":""}]
        for step in steps:
            technique=str((step or {}).get("technique") or "unknown").lower()
            group="all" if mode=="all" else technique
            target=groups.setdefault(group,[])
            for size,raw_qty in sizes.items():
                qty=max(0,int(float(raw_qty or 0)))
                if not qty: continue
                target.append({"article":item["description"],"sku":str(size_skus.get(size) or item["sku"] or ""),"color":color,"size":str(size),"quantity":qty,"team_name":"","personalization_name":"","number_text":"","techniques":technique,"position":str((step or {}).get("position") or ""),"motif":str((step or {}).get("motif") or ""),"shipping_group":"","product_id":str(item["product_id"] or "")})
    return {k:v for k,v in groups.items() if v}


@router.get("/sales/orders/{sales_order_id}/production-orders", dependencies=auth)
async def sales_order_production_orders(sales_order_id: str) -> dict[str, Any]:
    with _db() as conn:
        links=[dict(r) for r in conn.execute("SELECT * FROM production_order_links WHERE sales_order_id=? ORDER BY created_at",(sales_order_id,)).fetchall()]
    base_map={}
    if links:
        try:
            data=await asyncio.to_thread(_internal_json,"/api/orders?limit=2000","GET",None,30)
            base_map={str(x.get("id")):x for x in (data.get("items") or []) if isinstance(x,dict)}
        except Exception:
            base_map={}
    for link in links:
        base=base_map.get(str(link.get("base_order_id") or ""),{})
        if base:
            link["base_order"]=base; link["status"]=str(base.get("status") or link.get("status") or "planned")
    return {"ok":True,"items":links}


@router.post("/sales/orders/{sales_order_id}/production-orders", dependencies=auth)
async def sales_order_create_production_orders(sales_order_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}; mode=str(payload.get("mode") or "by_technique").lower()
    if mode not in {"by_technique","all"}: raise HTTPException(status_code=400,detail="Unbekannter Aufteilungsmodus.")
    with _db() as conn:
        order=conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone()
        if not order: raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        existing=int(conn.execute("SELECT COUNT(*) FROM production_order_links WHERE sales_order_id=?",(sales_order_id,)).fetchone()[0])
        if existing and not payload.get("allow_additional"):
            raise HTTPException(status_code=409,detail="Für diesen Auftrag wurden bereits Produktionsaufträge erzeugt.")
        groups=_business_production_groups(conn,sales_order_id,"all" if mode=="all" else "by_technique")
        if not groups: raise HTTPException(status_code=409,detail="Der Auftrag enthält keine produzierbaren Positionen.")
        production_defs=[]
        for group,rows in groups.items():
            pno=_business_next_no(conn,"production_order","PA")
            title=(order["subject"] or "Produktionsauftrag").strip()
            if mode!="all": title=f"{title} · {group.upper()}"
            production_defs.append((pno,group,title,rows))
    created=[]
    for pno,group,title,rows in production_defs:
        base_payload={"order_no":pno,"customer":order["customer_name"],"title":title,"due_date":order["due_date"],"items":rows}
        try:
            data=await asyncio.to_thread(_internal_json,"/api/orders","POST",base_payload,45)
            base_id=str(data.get("id") or data.get("order_id") or (data.get("item") or {}).get("id") or "") if isinstance(data,dict) else ""
            if not base_id:
                listing=await asyncio.to_thread(_internal_json,"/api/orders?limit=2000","GET",None,30)
                found=next((x for x in (listing.get("items") or []) if str(x.get("order_no") or "")==pno),None)
                base_id=str((found or {}).get("id") or "")
        except Exception as exc:
            raise HTTPException(status_code=502,detail=f"Produktionsauftrag {pno} konnte nicht im Produktionsserver angelegt werden: {exc}") from exc
        with _db() as conn:
            lid=str(uuid.uuid4()); now=_now()
            conn.execute("INSERT INTO production_order_links(id,production_order_no,sales_order_id,base_order_id,technique_group,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(lid,pno,sales_order_id,base_id,group,"planned",now,now))
            created.append({"id":lid,"production_order_no":pno,"sales_order_id":sales_order_id,"base_order_id":base_id,"technique_group":group,"status":"planned"})
    with _db() as conn:
        conn.execute("UPDATE sales_orders SET status='in_progress',updated_at=? WHERE id=? AND status IN ('draft','confirmed')",(_now(),sales_order_id))
    try:
        await asyncio.to_thread(_reconcile_inventory_from_orders)
    except Exception:
        pass
    return {"ok":True,"items":created}


@router.get("/business/search", dependencies=auth)
async def business_search(q: str = "", limit: int = 12) -> dict[str, Any]:
    q=str(q or "").strip()
    if len(q)<2: return {"ok":True,"items":[]}
    like=f"%{q}%"; cap=max(1,min(int(limit or 12),30)); out=[]
    with _db() as conn:
        for r in conn.execute("SELECT id,customer_no,company_name,first_name,last_name,email FROM crm_customers WHERE active=1 AND (customer_no LIKE ? OR company_name LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR email LIKE ?) LIMIT ?",(like,like,like,like,like,cap)).fetchall():
            out.append({"type":"customer","id":r["id"],"ref":r["customer_no"],"title":_business_customer_name(r),"subtitle":r["email"] or "Kunde"})
        for r in conn.execute("SELECT id,quote_no,customer_name,subject,status FROM sales_quotes WHERE quote_no LIKE ? OR customer_name LIKE ? OR subject LIKE ? ORDER BY updated_at DESC LIMIT ?",(like,like,like,cap)).fetchall():
            out.append({"type":"quote","id":r["id"],"ref":r["quote_no"],"title":r["subject"] or r["customer_name"],"subtitle":f"Angebot · {r['status']}"})
        for r in conn.execute("SELECT id,order_no,customer_name,subject,status FROM sales_orders WHERE order_no LIKE ? OR customer_name LIKE ? OR subject LIKE ? ORDER BY updated_at DESC LIMIT ?",(like,like,like,cap)).fetchall():
            out.append({"type":"sales_order","id":r["id"],"ref":r["order_no"],"title":r["subject"] or r["customer_name"],"subtitle":f"Auftrag · {r['status']}"})
        for r in conn.execute("SELECT id,invoice_no,direction,customer_name,supplier_name,subject,status FROM finance_invoices WHERE invoice_no LIKE ? OR customer_name LIKE ? OR supplier_name LIKE ? OR external_invoice_no LIKE ? OR subject LIKE ? ORDER BY updated_at DESC LIMIT ?",(like,like,like,like,like,cap)).fetchall():
            title=(r["customer_name"] if r["direction"]=="customer" else r["supplier_name"]) or r["subject"] or "Rechnung"
            out.append({"type":"invoice","id":r["id"],"ref":r["invoice_no"],"title":title,"subtitle":f"Rechnung · {r['status']}"})
    return {"ok":True,"items":out[:cap]}


@router.get("/woocommerce/status", dependencies=auth)
async def shared_woocommerce_status() -> dict[str, Any]:
    base = str(os.getenv("WC_URL", "") or "").strip().rstrip("/")
    configured = _woo_configured()
    result: dict[str, Any] = {
        "ok": True,
        "configured": configured,
        "url": base,
        "consumer_key_present": bool(str(os.getenv("WC_CONSUMER_KEY", "") or "").strip()),
        "consumer_secret_present": bool(str(os.getenv("WC_CONSUMER_SECRET", "") or "").strip()),
    }
    if configured:
        try:
            data = await asyncio.to_thread(_woo_json, "/products", {"per_page": 1, "page": 1, "status": "publish"}, 20)
            result["reachable"] = isinstance(data, list)
        except Exception as exc:
            result["reachable"] = False
            result["error"] = str(exc)
    else:
        result["reachable"] = False
    return result


@router.post("/inventory/sync-products", dependencies=auth)
async def inventory_sync_products(request: Request) -> dict[str, Any]:
    if not _woo_configured(): raise HTTPException(status_code=409,detail="WooCommerce ist noch nicht konfiguriert.")
    body=await request.json() if request.headers.get("content-type","").startswith("application/json") else {}
    max_pages=max(1,min(_safe_int((body or {}).get("max_pages"),20),100)); synced=0; stock_count=0
    for page in range(1,max_pages+1):
        rows=await asyncio.to_thread(_woo_json,"/products",{"per_page":100,"page":page,"status":"publish"},45)
        if not isinstance(rows,list) or not rows: break
        with _db() as conn:
            for product in rows:
                if not isinstance(product,dict): continue
                meta=_meta_dict(product); configs=_wsk_product_configs(product) or _woo_product_configs(product)
                manufacturer=_product_manufacturer(meta,product); supplier=_product_supplier(meta)
                images=product.get("images") or []; image=str(images[0].get("src") or "") if images and isinstance(images[0],dict) else ""
                aid=_ensure_inventory_article(conn,woo_product_id=str(product.get("id") or ""),name=str(product.get("name") or ""),sku=str(product.get("sku") or ""),manufacturer=manufacturer,supplier=supplier,image_url=image,raw=product); synced+=1
                for cfg in configs:
                    cfg_sizes=cfg.get("sizes") if isinstance(cfg.get("sizes"),list) else []
                    if not cfg_sizes: cfg_sizes=[""]
                    for size in cfg_sizes:
                        _ensure_stock_item(conn,article_id=aid,woo_product_id=str(product.get("id") or ""),sku=str(cfg.get("size_skus",{}).get(size) or cfg.get("sku") or product.get("sku") or ""),erp_code=str(cfg.get("erp_code") or ""),color=str(cfg.get("color") or ""),size=str(size or "")); stock_count+=1
            _refresh_stock_totals(conn)
        if len(rows)<100: break
    return {"ok":True,"products":synced,"stock_items":stock_count}

# --- WooCommerce Artikelsuche fuer manuelle HCA-Auftraege (v0.9.21) ---
def _woo_configured() -> bool:
    return bool(
        str(os.getenv("WC_URL", "") or "").strip()
        and str(os.getenv("WC_CONSUMER_KEY", "") or "").strip()
        and str(os.getenv("WC_CONSUMER_SECRET", "") or "").strip()
    )


def _woo_error(status: int, body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8", "replace")) if body else {}
        if isinstance(data, dict):
            return str(data.get("message") or data.get("error") or data.get("detail") or data)
    except Exception:
        pass
    text = body.decode("utf-8", "replace").strip()
    return text or f"WooCommerce HTTP {status}"


def _woo_json(path: str, params: dict[str, Any] | None = None, timeout: int = 35) -> Any:
    base = str(os.getenv("WC_URL", "") or "").strip().rstrip("/")
    key = str(os.getenv("WC_CONSUMER_KEY", "") or "").strip()
    secret = str(os.getenv("WC_CONSUMER_SECRET", "") or "").strip()
    if not base or not key or not secret:
        raise RuntimeError("WooCommerce ist auf dem Produktionsserver noch nicht konfiguriert.")
    url = base + "/wp-json/wc/v3" + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")}, doseq=True)
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + token, "Accept": "application/json", "User-Agent": "HCA-Produktionsmanager/0.9.24"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            return json.loads(raw.decode("utf-8", "replace")) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise RuntimeError(_woo_error(exc.code, body)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"WooCommerce nicht erreichbar: {exc.reason}") from exc


def _woo_request(path: str, method: str = "GET", payload: Any = None, *, api_namespace: str = "wc/v3", timeout: int = 45) -> Any:
    """Authenticated Woo request used by the isolated HCA integration.

    The existing product wizard endpoints remain read-only and untouched. Writes are
    only made through explicit HCA routes and require Woo REST keys with write access.
    """
    base = str(os.getenv("WC_URL", "") or "").strip().rstrip("/")
    key = str(os.getenv("WC_CONSUMER_KEY", "") or "").strip()
    secret = str(os.getenv("WC_CONSUMER_SECRET", "") or "").strip()
    if not base or not key or not secret:
        raise RuntimeError("WooCommerce ist auf dem Produktionsserver noch nicht konfiguriert.")
    clean_path = path if str(path).startswith("/") else "/" + str(path)
    url = f"{base}/wp-json/{api_namespace.strip('/')}{clean_path}"
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": "Basic " + token, "Accept": "application/json", "User-Agent": "HCA-Produktionsmanager/0.13.0"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=str(method or "GET").upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            return json.loads(raw.decode("utf-8", "replace")) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_woo_error(exc.code, exc.read())) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"WooCommerce nicht erreichbar: {exc.reason}") from exc


def _woo_attr_key(name: Any) -> str:
    value = str(name or "").replace("ß", "ss").replace("ẞ", "SS")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "", value)
    if value in {"grosse", "groesse", "size", "sizes", "konfektionsgrosse", "konfektionsgroesse"} or "size" in value or "grosse" in value or "groesse" in value:
        return "size"
    if value in {"farbe", "color", "colour", "farbton"} or "farbe" in value or "color" in value or "colour" in value:
        return "color"
    return value


def _woo_attr_values(attributes: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(attributes, list):
        return result
    for attr in attributes:
        if not isinstance(attr, dict):
            continue
        key = _woo_attr_key(attr.get("name") or attr.get("slug"))
        option = str(attr.get("option") or "").strip()
        if key and option:
            result[key] = option
    return result


def _woo_parent_attr_options(product: dict[str, Any], wanted: str) -> list[str]:
    for attr in product.get("attributes") or []:
        if not isinstance(attr, dict) or _woo_attr_key(attr.get("name") or attr.get("slug")) != wanted:
            continue
        options = attr.get("options") or []
        return [str(x).strip() for x in options if str(x).strip()]
    return []


def _woo_product_variations(product_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Bekleidungsartikel liegen normalerweise deutlich unter 300 Varianten. Drei Seiten vermeiden
    # trotzdem das Abschneiden groesserer Farb-/Groessenmatrizen.
    for page in range(1, 4):
        data = _woo_json(f"/products/{int(product_id)}/variations", {"per_page": 100, "page": page, "status": "publish"})
        if not isinstance(data, list) or not data:
            break
        rows.extend(x for x in data if isinstance(x, dict))
        if len(data) < 100:
            break
    return rows


def _woo_product_configs(product: dict[str, Any], matched_variation_ids: set[int] | None = None) -> list[dict[str, Any]]:
    matched_variation_ids = matched_variation_ids or set()
    wsk_configs = _wsk_product_configs(product)
    if wsk_configs:
        return wsk_configs
    product_id = int(product.get("id") or 0)
    name = str(product.get("name") or "").strip()
    base_sku = str(product.get("sku") or "").strip()
    images = product.get("images") or []
    image = str(images[0].get("src") or "") if images and isinstance(images[0], dict) else ""
    weight = str(product.get("weight") or "").strip()
    dimensions = product.get("dimensions") if isinstance(product.get("dimensions"), dict) else {}
    product_type = str(product.get("type") or "").strip().lower()
    if product_type != "variable":
        colors = _woo_parent_attr_options(product, "color")
        return [{
            "key": f"{product_id}:simple",
            "product_id": product_id,
            "name": name,
            "sku": base_sku,
            "color": colors[0] if len(colors) == 1 else "",
            "sizes": _woo_parent_attr_options(product, "size"),
            "size_skus": {},
            "matched_sku": base_sku,
            "image": image,
            "weight": weight,
            "dimensions": dimensions,
            "stock_status": str(product.get("stock_status") or ""),
            "price": product.get("price"), "regular_price": product.get("regular_price"),
        }]

    variations = _woo_product_variations(product_id)
    groups: dict[str, list[dict[str, Any]]] = {}
    for v in variations:
        attrs = _woo_attr_values(v.get("attributes"))
        color = attrs.get("color", "")
        groups.setdefault(color, []).append(v)
    if not groups:
        colors = _woo_parent_attr_options(product, "color") or [""]
        groups = {c: [] for c in colors}

    parent_size_order = _woo_parent_attr_options(product, "size")
    configs: list[dict[str, Any]] = []
    for color, vars_for_color in groups.items():
        size_skus: dict[str, str] = {}
        sizes: list[str] = []
        matched_sku = ""
        matched = False
        for v in vars_for_color:
            attrs = _woo_attr_values(v.get("attributes"))
            size = attrs.get("size", "")
            sku = str(v.get("sku") or "").strip()
            vid = int(v.get("id") or 0)
            if size and size not in sizes:
                sizes.append(size)
            if size and sku:
                size_skus[size] = sku
            if vid in matched_variation_ids:
                matched = True
                matched_sku = sku
        if parent_size_order:
            ordered = [s for s in parent_size_order if s in sizes]
            ordered += [s for s in sizes if s not in ordered]
            sizes = ordered
        config_sku = base_sku or matched_sku
        configs.append({
            "key": f"{product_id}:{color or '-'}",
            "product_id": product_id,
            "name": name,
            "sku": config_sku,
            "color": color,
            "sizes": sizes,
            "size_skus": size_skus,
            "matched_sku": matched_sku,
            "image": image,
            "weight": weight,
            "dimensions": dimensions,
            "stock_status": str(product.get("stock_status") or ""),
            "price": product.get("price"), "regular_price": product.get("regular_price"),
            "matched": matched,
        })
    configs.sort(key=lambda x: (0 if x.get("matched") else 1, str(x.get("color") or "").lower()))
    return configs


def _search_norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _woo_search_products(query: str, limit: int = 24) -> list[dict[str, Any]]:
    query = str(query or "").strip()
    if len(query) < 2:
        return []
    per_page = max(1, min(int(limit or 24), 50))
    qn = _search_norm(query)
    cache_key = f"{qn}:{per_page}"
    cached = _PRODUCT_SEARCH_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _PRODUCT_SEARCH_CACHE_TTL:
        return cached[1]

    # Zuerst den zentralen Synology-Artikelcache durchsuchen. Dadurch gibt es beim Tippen
    # keinen WooCommerce-Roundtrip. ID.001 ist dadurch auch mit ID001 auffindbar.
    local_products: list[dict[str, Any]] = []
    try:
        with _db() as conn:
            rows = conn.execute("SELECT raw_json,name,sku FROM inventory_articles ORDER BY updated_at DESC").fetchall()
        scored=[]
        for row in rows:
            raw=_loads(row["raw_json"], {})
            if not isinstance(raw,dict): raw={}
            name=str(raw.get("name") or row["name"] or ""); sku=str(raw.get("sku") or row["sku"] or "")
            hay_name=_search_norm(name); hay_sku=_search_norm(sku)
            if qn not in hay_name and qn not in hay_sku: continue
            score=(0 if hay_sku.startswith(qn) else 1 if qn in hay_sku else 2 if hay_name.startswith(qn) else 3, name.lower())
            scored.append((score,raw))
        scored.sort(key=lambda x:x[0])
        for _,product in scored[:12]:
            local_products.extend(_wsk_product_configs(product) or _woo_product_configs(product))
            if len(local_products)>=per_page*3: break
    except Exception:
        local_products=[]
    if local_products:
        result=local_products[:max(1,min(per_page*3,60))]
        _PRODUCT_SEARCH_CACHE[cache_key]=(time.time(),result)
        return result

    # Fallback: Shop direkt durchsuchen, falls der Artikelcache noch nicht synchronisiert wurde.
    variants=[]
    for candidate in (query, re.sub(r"[. _-]+", "", query)):
        if not candidate: continue
        try:
            rows=_woo_json("/products", {"search": candidate, "per_page": per_page, "status":"publish"})
            if isinstance(rows,list): variants.extend(rows)
        except Exception: pass
        try:
            rows=_woo_json("/products", {"sku": candidate, "per_page": per_page, "status":"publish"})
            if isinstance(rows,list): variants.extend(rows)
        except Exception: pass
    parents={}
    for row in variants:
        if not isinstance(row,dict): continue
        pid=int(row.get("parent_id") or row.get("id") or 0)
        if not pid: continue
        if row.get("parent_id"):
            try: row=_woo_json(f"/products/{pid}")
            except Exception: continue
        parents[pid]=row
    result=[]
    for product in parents.values(): result.extend(_wsk_product_configs(product) or _woo_product_configs(product))
    result.sort(key=lambda x:(0 if qn in _search_norm(x.get("sku")) else 1,0 if qn in _search_norm(x.get("name")) else 1,str(x.get("name") or "").lower()))
    result=result[:max(1,min(per_page*3,60))]
    _PRODUCT_SEARCH_CACHE[cache_key]=(time.time(),result)
    return result


@router.get("/woocommerce/products/search", dependencies=auth)
async def search_woocommerce_products(q: str = "", limit: int = 24) -> dict[str, Any]:
    if not _woo_configured():
        raise HTTPException(status_code=409, detail="WooCommerce ist auf dem Produktionsserver noch nicht konfiguriert.")
    q = str(q or "").strip()
    if len(q) < 2:
        return {"ok": True, "items": [], "query": q}
    try:
        items = await asyncio.to_thread(_woo_search_products, q, limit)
        return {"ok": True, "items": items, "query": q}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WooCommerce-Artikelsuche fehlgeschlagen: {exc}") from exc


@router.get("/woocommerce/products/{product_id}/wizard-config", dependencies=auth)
async def woocommerce_product_wizard_config(product_id: int) -> dict[str, Any]:
    """Returns the normalized product options used by the public WooCommerce wizard."""
    if product_id <= 0:
        raise HTTPException(status_code=400, detail="Produkt-ID fehlt.")
    try:
        response = await asyncio.to_thread(
            _woo_form_post,
            "/?wc-ajax=wsk_hca_product_config",
            {"product_id": product_id},
        )
        if not isinstance(response, dict) or not response.get("success"):
            message = (response or {}).get("data") if isinstance(response, dict) else ""
            if isinstance(message, dict):
                message = message.get("message") or ""
            raise RuntimeError(str(message or "Produktkonfiguration konnte nicht geladen werden."))
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        return {"ok": True, **data, "source": "woocommerce-wizard"}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"WooCommerce-Wizarddaten konnten nicht geladen werden: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# HCA Finanzen / Rechnungen / Lexware Office (v0.10.2)
# ---------------------------------------------------------------------------

FINANCE_INVOICE_STATUSES = {"draft", "open", "paid", "voided", "cancelled"}
LEXWARE_VOUCHER_TYPES = {"salesinvoice", "salescreditnote", "purchaseinvoice", "purchasecreditnote", "invoice", "downpaymentinvoice", "creditnote"}


def _finance_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _finance_due(days: int = 14) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=max(0, int(days)))).isoformat()


def _finance_deeplink(voucher_type: str, voucher_id: str) -> str:
    vt = str(voucher_type or "").lower()
    vid = urllib.parse.quote(str(voucher_id or ""), safe="")
    if not vid:
        return ""
    if vt in {"salesinvoice", "salescreditnote", "purchaseinvoice", "purchasecreditnote"}:
        return f"https://app.lexware.de/permalink/vouchers/view/{vid}"
    if vt in {"invoice", "downpaymentinvoice"}:
        return f"https://app.lexware.de/permalink/invoices/view/{vid}"
    if vt == "creditnote":
        return f"https://app.lexware.de/permalink/credit-notes/view/{vid}"
    return "https://app.lexware.de/vouchers"


def _finance_item_values(raw: dict[str, Any]) -> dict[str, Any]:
    qty = max(0.0, float(raw.get("quantity") or 0))
    if qty <= 0:
        qty = 1.0
    unit_price = float(raw.get("unit_price") or 0)
    discount = max(0.0, min(100.0, float(raw.get("discount_pct") or 0)))
    tax_rate = max(0.0, float(raw.get("tax_rate") if raw.get("tax_rate") is not None else 19))
    net = qty * unit_price * (1.0 - discount / 100.0)
    tax = net * tax_rate / 100.0
    return {
        "sku": str(raw.get("sku") or "").strip(),
        "description": str(raw.get("description") or raw.get("article") or "").strip(),
        "quantity": qty,
        "unit": str(raw.get("unit") or "Stk.").strip() or "Stk.",
        "unit_price": round(unit_price, 4),
        "discount_pct": round(discount, 2),
        "tax_rate": round(tax_rate, 2),
        "net_total": round(net, 2),
        "tax_total": round(tax, 2),
        "gross_total": round(net + tax, 2),
        "source_item_id": str(raw.get("source_item_id") or raw.get("id") or ""),
    }


def _finance_replace_items(conn: sqlite3.Connection, invoice_id: str, items: list[dict[str, Any]]) -> dict[str, float]:
    conn.execute("DELETE FROM finance_invoice_items WHERE invoice_id=?", (invoice_id,))
    net = tax = gross = 0.0
    now = _now(); pos = 10
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        item = _finance_item_values(raw)
        if not item["description"]:
            continue
        conn.execute(
            "INSERT INTO finance_invoice_items(id,invoice_id,position_no,sku,description,quantity,unit,unit_price,discount_pct,tax_rate,net_total,tax_total,gross_total,source_item_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), invoice_id, int(raw.get("position_no") or pos), item["sku"], item["description"], item["quantity"], item["unit"], item["unit_price"], item["discount_pct"], item["tax_rate"], item["net_total"], item["tax_total"], item["gross_total"], item["source_item_id"], now, now),
        )
        net += item["net_total"]; tax += item["tax_total"]; gross += item["gross_total"]; pos += 10
    return {"net": round(net,2), "tax": round(tax,2), "gross": round(gross,2)}


def _finance_store_attachment(invoice_id: str, filename: str, mime: str, data_b64: str) -> tuple[str, str, str]:
    if not data_b64:
        return "", "", ""
    try:
        payload = data_b64.split(",", 1)[-1]
        raw = base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Belegdatei konnte nicht gelesen werden.") from exc
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Belegdatei ist größer als 8 MB.")
    safe_name = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß._-]+", "_", str(filename or "beleg.pdf")).strip("._") or "beleg.pdf"
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".xml"}:
        raise HTTPException(status_code=400, detail="Erlaubt sind PDF, JPG, PNG oder XML.")
    INVOICE_FILE_DIR.mkdir(parents=True, exist_ok=True)
    path = INVOICE_FILE_DIR / f"{invoice_id}_{safe_name}"
    path.write_bytes(raw)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    guessed = mime or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return str(path), safe_name, guessed


def _finance_invoice_dict(conn: sqlite3.Connection, row: sqlite3.Row, include_items: bool = True) -> dict[str, Any]:
    d = dict(row)
    d["billing"] = _loads(d.pop("billing_json", "{}"), {})
    d["shipping"] = _loads(d.pop("shipping_json", "{}"), {})
    d["lexware"] = bool(d.get("lexware_voucher_id"))
    d["has_file"] = bool(d.get("file_path") and Path(str(d.get("file_path"))).exists())
    d["record_type"] = "local"
    if include_items:
        d["items"] = [dict(x) for x in conn.execute("SELECT * FROM finance_invoice_items WHERE invoice_id=? ORDER BY position_no,id", (row["id"],)).fetchall()]
    d["lexware_deeplink"] = d.get("lexware_deeplink") or _finance_deeplink(str(d.get("lexware_voucher_type") or ""), str(d.get("lexware_voucher_id") or ""))
    credit = conn.execute("SELECT * FROM finance_credit_notes WHERE invoice_id=? ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
    if credit:
        c = dict(credit)
        labels = {"offset":"Mit offener Forderung verrechnet","refund":"Rückzahlung an Kunden ausstehend","customer_credit":"Als Kundenguthaben verbucht"}
        d["credit_note_id"] = c.get("id") or ""
        d["credit_note_no"] = c.get("credit_note_no") or ""
        d["credit_settlement_method"] = c.get("settlement_method") or ""
        d["credit_settlement_label"] = labels.get(str(c.get("settlement_method") or ""), "")
        d["credit_lexware_deeplink"] = c.get("lexware_deeplink") or ""
    return d


def _lexware_settings_load() -> dict[str, Any]:
    data: dict[str, Any] = {}
    if LEXWARE_SETTINGS_FILE.exists():
        try:
            obj = json.loads(LEXWARE_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(obj, dict): data = obj
        except Exception:
            data = {}
    env_token = str(os.getenv("LEXWARE_API_TOKEN", "") or "").strip()
    if env_token:
        data["token"] = env_token
        data["token_source"] = "environment"
    data.setdefault("base_url", LEXWARE_BASE)
    data.setdefault("sales_category_id", "")
    data.setdefault("sales_category_name", "")
    data.setdefault("purchase_category_id", "")
    data.setdefault("purchase_category_name", "")
    data.setdefault("last_sync", "")
    return data


def _lexware_settings_save(values: dict[str, Any]) -> dict[str, Any]:
    current = _lexware_settings_load()
    if str(os.getenv("LEXWARE_API_TOKEN", "") or "").strip():
        # Environment token has priority; never overwrite it from the UI.
        token = current.get("token", "")
    else:
        token = str(values.get("token") or current.get("token") or "").strip()
    data = {
        "token": token,
        "base_url": LEXWARE_BASE,
        "sales_category_id": str(values.get("sales_category_id") if values.get("sales_category_id") is not None else current.get("sales_category_id") or "").strip(),
        "sales_category_name": str(values.get("sales_category_name") if values.get("sales_category_name") is not None else current.get("sales_category_name") or "").strip(),
        "purchase_category_id": str(values.get("purchase_category_id") if values.get("purchase_category_id") is not None else current.get("purchase_category_id") or "").strip(),
        "purchase_category_name": str(values.get("purchase_category_name") if values.get("purchase_category_name") is not None else current.get("purchase_category_name") or "").strip(),
        "last_sync": str(values.get("last_sync") if values.get("last_sync") is not None else current.get("last_sync") or "").strip(),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LEXWARE_SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try: os.chmod(LEXWARE_SETTINGS_FILE, 0o600)
    except Exception: pass
    return data


def _lexware_public_settings() -> dict[str, Any]:
    data = _lexware_settings_load(); token = str(data.get("token") or "")
    return {
        "configured": bool(token),
        "token_source": data.get("token_source") or ("file" if token else ""),
        "token_hint": ("••••" + token[-4:]) if token else "",
        "base_url": LEXWARE_BASE,
        "sales_category_id": data.get("sales_category_id") or "",
        "sales_category_name": data.get("sales_category_name") or "",
        "purchase_category_id": data.get("purchase_category_id") or "",
        "purchase_category_name": data.get("purchase_category_name") or "",
        "last_sync": data.get("last_sync") or "",
    }


def _lexware_request(path: str, method: str = "GET", payload: Any = None, accept: str = "application/json", timeout: int = 30) -> Any:
    settings = _lexware_settings_load(); token = str(settings.get("token") or "").strip()
    if not token:
        raise RuntimeError("Lexware-API-Schlüssel ist noch nicht hinterlegt.")
    url = LEXWARE_BASE.rstrip("/") + (path if path.startswith("/") else "/" + path)
    headers = {"Authorization": f"Bearer {token}", "Accept": accept, "User-Agent": "HCA-Manager/0.10.2"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if accept == "application/json" or "json" in str(resp.headers.get("Content-Type", "")):
                return json.loads(raw.decode("utf-8")) if raw else {}
            return raw
    except urllib.error.HTTPError as exc:
        try: detail = exc.read().decode("utf-8", "replace")
        except Exception: detail = str(exc)
        raise RuntimeError(f"Lexware HTTP {exc.code}: {detail[:600]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Lexware-Verbindung fehlgeschlagen: {exc}") from exc


def _lexware_upload_file(voucher_id: str, file_path: str, filename: str, mime: str) -> Any:
    settings = _lexware_settings_load(); token = str(settings.get("token") or "").strip()
    if not token: raise RuntimeError("Lexware-API-Schlüssel ist noch nicht hinterlegt.")
    path = Path(file_path)
    if not path.exists(): raise RuntimeError("Die lokale Belegdatei wurde nicht gefunden.")
    raw = path.read_bytes()
    if len(raw) > 5 * 1024 * 1024: raise RuntimeError("Lexware akzeptiert Belegdateien bis 5 MB.")
    boundary = "----HCALexware" + secrets.token_hex(12)
    safe = str(filename or path.name).replace('"', '')
    mtype = mime or mimetypes.guess_type(safe)[0] or "application/octet-stream"
    prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe}\"\r\nContent-Type: {mtype}\r\n\r\n").encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = prefix + raw + suffix
    req = urllib.request.Request(
        f"{LEXWARE_BASE}/v1/vouchers/{urllib.parse.quote(str(voucher_id),safe='')}/files",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept":"application/json", "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent":"HCA-Manager/0.10.2"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read(); return json.loads(data.decode("utf-8")) if data else {}
    except urllib.error.HTTPError as exc:
        try: detail=exc.read().decode("utf-8","replace")
        except Exception: detail=str(exc)
        raise RuntimeError(f"Lexware-Dateiupload HTTP {exc.code}: {detail[:600]}") from exc


def _lexware_sync_vouchers_blocking() -> dict[str, Any]:
    all_items: list[dict[str, Any]] = []
    for page in range(0, 8):
        data = _lexware_request(f"/v1/voucherlist?voucherType=salesinvoice,purchaseinvoice,invoice,downpaymentinvoice,salescreditnote,purchasecreditnote,creditnote&size=250&page={page}&sort=updatedDate,DESC")
        content = data.get("content") if isinstance(data, dict) else []
        if not isinstance(content, list): content = []
        all_items.extend(x for x in content if isinstance(x, dict))
        if len(content) < 250: break
    now = _now()
    with _db() as conn:
        local_map = {str(r["lexware_voucher_id"]): str(r["id"]) for r in conn.execute("SELECT id,lexware_voucher_id FROM finance_invoices WHERE lexware_voucher_id<>''").fetchall()}
        for item in all_items:
            vid = str(item.get("id") or "").strip()
            if not vid: continue
            vt = str(item.get("voucherType") or item.get("type") or "").strip()
            raw_json = _json(item)
            lower = raw_json.lower()
            source_guess = "woocommerce" if "woocommerce" in lower or "woo commerce" in lower else "lexware"
            deeplink = _finance_deeplink(vt, vid)
            conn.execute(
                "INSERT INTO finance_lexware_vouchers(lexware_id,voucher_type,voucher_number,contact_id,contact_name,total_amount,open_amount,currency,voucher_status,voucher_date,archived,source_guess,raw_json,lexware_deeplink,synced_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(lexware_id) DO UPDATE SET voucher_type=excluded.voucher_type,voucher_number=excluded.voucher_number,contact_id=excluded.contact_id,contact_name=excluded.contact_name,total_amount=excluded.total_amount,open_amount=excluded.open_amount,currency=excluded.currency,voucher_status=excluded.voucher_status,voucher_date=excluded.voucher_date,archived=excluded.archived,source_guess=excluded.source_guess,raw_json=excluded.raw_json,lexware_deeplink=excluded.lexware_deeplink,synced_at=excluded.synced_at,updated_at=excluded.updated_at",
                (vid,vt,str(item.get("voucherNumber") or ""),str(item.get("contactId") or ""),str(item.get("contactName") or ""),float(item.get("totalAmount") or 0),None if item.get("openAmount") is None else float(item.get("openAmount") or 0),str(item.get("currency") or "EUR"),str(item.get("voucherStatus") or ""),str(item.get("voucherDate") or ""),1 if item.get("archived") else 0,source_guess,raw_json,deeplink,now,str(item.get("updatedDate") or now)),
            )
            if vid in local_map:
                open_amount = None if item.get("openAmount") is None else float(item.get("openAmount") or 0)
                vstatus = str(item.get("voucherStatus") or "")
                pstatus = "paid" if vstatus in {"paid","paidoff"} or open_amount == 0 else ("open" if open_amount is not None else "")
                conn.execute("UPDATE finance_invoices SET lexware_status=?,lexware_open_amount=?,payment_status=CASE WHEN ?<>'' THEN ? ELSE payment_status END,lexware_deeplink=?,lexware_synced_at=?,updated_at=? WHERE lexware_voucher_id=?", (vstatus,open_amount,pstatus,pstatus,deeplink,now,now,vid))
    settings=_lexware_settings_load(); settings["last_sync"]=now; _lexware_settings_save(settings)
    return {"count": len(all_items), "last_sync": now}


def _finance_external_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row); vt=str(d.get("voucher_type") or "")
    direction = "supplier" if vt in {"purchaseinvoice","purchasecreditnote"} else "customer"
    total=float(d.get("total_amount") or 0); open_amount=d.get("open_amount")
    return {
        "id": "lexware:" + str(d.get("lexware_id") or ""), "lexware_voucher_id": d.get("lexware_id") or "", "record_type":"external", "direction":direction,
        "source": "woocommerce" if d.get("source_guess")=="woocommerce" else "lexware_external", "invoice_no": d.get("voucher_number") or "", "external_invoice_no": d.get("voucher_number") or "",
        "customer_name": d.get("contact_name") or "", "supplier_name": d.get("contact_name") or "", "subject":"", "status": d.get("voucher_status") or "", "payment_status": "paid" if str(d.get("voucher_status") or "") in {"paid","paidoff"} or open_amount==0 else "open",
        "invoice_date": d.get("voucher_date") or "", "due_date":"", "currency":d.get("currency") or "EUR", "total_net":0, "total_tax":0, "total_gross":total,
        "lexware":True, "lexware_voucher_type":vt, "lexware_status":d.get("voucher_status") or "", "lexware_open_amount":open_amount, "lexware_deeplink":d.get("lexware_deeplink") or _finance_deeplink(vt,str(d.get("lexware_id") or "")), "has_file":False,
    }


@router.get("/finance/invoices", dependencies=auth)
async def finance_invoices(q: str = "", direction: str = "all", status: str = "all", limit: int = 1000) -> dict[str, Any]:
    q=str(q or "").strip(); direction=str(direction or "all").lower(); status=str(status or "all").lower(); cap=max(1,min(int(limit or 1000),3000))
    items: list[dict[str, Any]]=[]
    with _db() as conn:
        local=conn.execute("SELECT * FROM finance_invoices ORDER BY invoice_date DESC,updated_at DESC LIMIT ?",(cap,)).fetchall()
        local_lex={str(r["lexware_voucher_id"] or "") for r in local if str(r["lexware_voucher_id"] or "")}
        items.extend(_finance_invoice_dict(conn,r,False) for r in local)
        for row in conn.execute("SELECT * FROM finance_lexware_vouchers ORDER BY voucher_date DESC,updated_at DESC LIMIT ?",(cap,)).fetchall():
            if str(row["lexware_id"] or "") in local_lex: continue
            items.append(_finance_external_dict(row))
    if direction in {"customer","supplier"}: items=[x for x in items if x.get("direction")==direction]
    if status=="open": items=[x for x in items if str(x.get("status") or "") not in {"paid","paidoff","voided","cancelled"}]
    elif status=="paid": items=[x for x in items if str(x.get("payment_status") or "")=="paid" or str(x.get("status") or "") in {"paid","paidoff"}]
    if q:
        low=q.lower(); items=[x for x in items if low in " ".join(str(x.get(k) or "") for k in ("invoice_no","external_invoice_no","customer_name","supplier_name","subject","customer_reference","purchase_reference")).lower()]
    items=sorted(items,key=lambda x:(str(x.get("invoice_date") or ""),str(x.get("updated_at") or "")),reverse=True)[:cap]
    return {"ok":True,"items":items,"lexware":_lexware_public_settings()}


@router.get("/finance/invoices/{invoice_id}", dependencies=auth)
async def finance_invoice_get(invoice_id: str) -> dict[str, Any]:
    if str(invoice_id).startswith("lexware:"):
        vid=str(invoice_id).split(":",1)[1]
        with _db() as conn:
            row=conn.execute("SELECT * FROM finance_lexware_vouchers WHERE lexware_id=?",(vid,)).fetchone()
            if not row: raise HTTPException(status_code=404,detail="Lexware-Beleg nicht gefunden.")
            return {"ok":True,"item":_finance_external_dict(row)}
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Rechnung nicht gefunden.")
        return {"ok":True,"item":_finance_invoice_dict(conn,row,True)}


def _finance_customer_invoice_from_order(conn: sqlite3.Connection, order: sqlite3.Row, payload: dict[str, Any]) -> dict[str, Any]:
    term_days=int(_payment_term_for_customer(conn,str(order["customer_id"] or ""),str(order["payment_term_id"] or "")).get("days") or 0)
    iid=str(uuid.uuid4()); ino=f"DRAFT-{iid[:8].upper()}"; now=_now(); invoice_date=str(payload.get("invoice_date") or _finance_today()); due_date=str(payload.get("due_date") or _finance_due(int(payload.get("payment_days") if payload.get("payment_days") is not None else term_days)))
    items=[]
    for r in conn.execute("SELECT * FROM sales_order_items WHERE sales_order_id=? ORDER BY position_no,id",(order["id"],)).fetchall():
        config=_loads(r["config_json"],{}) if "config_json" in r.keys() else {}
        extra_unit=0.0; setup=0.0
        for step in (config.get("production_steps") if isinstance(config,dict) and isinstance(config.get("production_steps"),list) else []):
            if not isinstance(step,dict): continue
            extra_unit += max(0.0,float(step.get("unit_price") or 0)); setup += max(0.0,float(step.get("setup_price") or 0))
        qty=float(r["quantity"] or 1); unit=float(r["unit_price"] or 0)+extra_unit
        items.append({"source_item_id":r["id"],"sku":r["sku"],"description":r["description"],"quantity":qty,"unit":r["unit"],"unit_price":unit,"discount_pct":r["discount_pct"],"tax_rate":r["tax_rate"]})
        if setup>0: items.append({"source_item_id":r["id"],"sku":"","description":f"Einrichtung / Druckvorbereitung · {r['description']}","quantity":1,"unit":"Pausch.","unit_price":setup,"discount_pct":0,"tax_rate":r["tax_rate"]})
    conn.execute("INSERT INTO finance_invoices(id,invoice_no,direction,source,sales_order_id,customer_id,customer_name,supplier_name,external_invoice_no,subject,status,payment_status,invoice_date,due_date,currency,billing_json,shipping_json,customer_reference,purchase_reference,notes,total_net,total_tax,total_gross,tax_rate,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,ino,"customer","hca",order["id"],order["customer_id"],order["customer_name"],"","",str(payload.get("subject") or order["subject"] or f"Rechnung zu {order['order_no']}"),"draft","open",invoice_date,due_date,"EUR",order["billing_json"],order["shipping_json"],order["customer_reference"],"",str(payload.get("notes") or ""),0,0,0,19,now,now))
    conn.execute("UPDATE finance_invoices SET source_quote_id=?,payment_term_id=?,payment_term_text=? WHERE id=?",(str(order["source_quote_id"] or ""),str(order["payment_term_id"] or ""),str(order["payment_term_text"] or ""),iid))
    totals=_finance_replace_items(conn,iid,items)
    conn.execute("UPDATE finance_invoices SET total_net=?,total_tax=?,total_gross=?,updated_at=? WHERE id=?",(totals["net"],totals["tax"],totals["gross"],_now(),iid))
    return _finance_invoice_dict(conn,conn.execute("SELECT * FROM finance_invoices WHERE id=?",(iid,)).fetchone(),True)


@router.post("/finance/invoices/from-order/{sales_order_id}", dependencies=auth)
async def finance_invoice_from_order(sales_order_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    with _db() as conn:
        order=conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone()
        if not order: raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        if not payload.get("allow_additional"):
            existing=conn.execute("SELECT * FROM finance_invoices WHERE sales_order_id=? AND direction='customer' AND status NOT IN ('voided','cancelled') ORDER BY created_at LIMIT 1",(sales_order_id,)).fetchone()
            if existing: return {"ok":True,"item":_finance_invoice_dict(conn,existing,True),"already_exists":True}
        return {"ok":True,"item":_finance_customer_invoice_from_order(conn,order,payload)}


@router.post("/finance/invoices", dependencies=auth)
async def finance_invoice_create(request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}; direction=str(payload.get("direction") or "customer").lower()
    if direction not in {"customer","supplier"}: raise HTTPException(status_code=400,detail="Ungültige Rechnungsart.")
    with _db() as conn:
        now=_now(); iid=str(uuid.uuid4()); ino=(f"DRAFT-{iid[:8].upper()}" if direction=="customer" else _business_next_no(conn,"supplier_invoice","ER"))
        invoice_date=str(payload.get("invoice_date") or _finance_today()); due_date=str(payload.get("due_date") or _finance_due(14)); customer_id=str(payload.get("customer_id") or ""); customer_name=""; billing={}; shipping={}
        if direction=="customer":
            customer=conn.execute("SELECT * FROM crm_customers WHERE id=? AND active=1",(customer_id,)).fetchone() if customer_id else conn.execute("SELECT * FROM crm_customers WHERE active=1 AND is_default=1 ORDER BY updated_at DESC LIMIT 1").fetchone()
            if not customer: raise HTTPException(status_code=400,detail="Bitte einen Kunden auswählen oder einen Standardkunden festlegen.")
            customer_id=str(customer["id"]); customer_name=_business_customer_name(customer); billing,shipping=_business_customer_snapshot(conn,customer,str(payload.get("contact_id") or ""),str(payload.get("billing_address_id") or ""),str(payload.get("shipping_address_id") or ""))
        supplier_name=str(payload.get("supplier_name") or "").strip()
        if direction=="supplier" and not supplier_name: raise HTTPException(status_code=400,detail="Bitte Lieferant angeben.")
        items=payload.get("items") if isinstance(payload.get("items"),list) else []
        if direction=="supplier" and not items:
            net=float(payload.get("total_net") or 0); tax=float(payload.get("total_tax") or 0); gross=float(payload.get("total_gross") or 0); rate=float(payload.get("tax_rate") if payload.get("tax_rate") is not None else 19)
            if net<=0 and gross>0: net=max(0,gross-tax)
            if gross<=0: gross=net+tax
            items=[{"description":str(payload.get("subject") or "Lieferantenrechnung"),"quantity":1,"unit":"Beleg","unit_price":net,"discount_pct":0,"tax_rate":rate}]
        conn.execute("INSERT INTO finance_invoices(id,invoice_no,direction,source,sales_order_id,customer_id,customer_name,supplier_name,external_invoice_no,subject,status,payment_status,invoice_date,due_date,currency,billing_json,shipping_json,customer_reference,purchase_reference,notes,total_net,total_tax,total_gross,tax_rate,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,ino,direction,"hca",str(payload.get("sales_order_id") or ""),customer_id,customer_name,supplier_name,str(payload.get("external_invoice_no") or "").strip(),str(payload.get("subject") or ("Kundenrechnung" if direction=="customer" else "Lieferantenrechnung")),"draft" if direction=="customer" else "open","open",invoice_date,due_date,"EUR",_json(billing),_json(shipping),str(payload.get("customer_reference") or ""),str(payload.get("purchase_reference") or ""),str(payload.get("notes") or ""),0,0,0,float(payload.get("tax_rate") if payload.get("tax_rate") is not None else 19),now,now))
        totals=_finance_replace_items(conn,iid,items)
        # Supplier invoices may include a tax value that differs slightly due to supplier rounding. Preserve user totals if supplied.
        if direction=="supplier" and payload.get("total_gross") not in (None,""):
            totals={"net":round(float(payload.get("total_net") or totals["net"]),2),"tax":round(float(payload.get("total_tax") or totals["tax"]),2),"gross":round(float(payload.get("total_gross") or totals["gross"]),2)}
        path=name=mime=""
        att=payload.get("attachment") if isinstance(payload.get("attachment"),dict) else {}
        if att.get("data"):
            path,name,mime=_finance_store_attachment(iid,str(att.get("name") or "beleg.pdf"),str(att.get("mime") or ""),str(att.get("data") or ""))
        conn.execute("UPDATE finance_invoices SET total_net=?,total_tax=?,total_gross=?,file_path=?,file_name=?,file_mime=?,updated_at=? WHERE id=?",(totals["net"],totals["tax"],totals["gross"],path,name,mime,_now(),iid))
        return {"ok":True,"item":_finance_invoice_dict(conn,conn.execute("SELECT * FROM finance_invoices WHERE id=?",(iid,)).fetchone(),True)}


@router.put("/finance/invoices/{invoice_id}", dependencies=auth)
async def finance_invoice_update(invoice_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Rechnung nicht gefunden.")
        if row["status"]!="draft": raise HTTPException(status_code=409,detail="Nur Entwurfsrechnungen können geändert werden.")
        items=payload.get("items") if isinstance(payload.get("items"),list) else [dict(x) for x in conn.execute("SELECT * FROM finance_invoice_items WHERE invoice_id=? ORDER BY position_no",(invoice_id,)).fetchall()]
        totals=_finance_replace_items(conn,invoice_id,items)
        conn.execute("UPDATE finance_invoices SET subject=?,invoice_date=?,due_date=?,customer_reference=?,notes=?,total_net=?,total_tax=?,total_gross=?,updated_at=? WHERE id=?",(str(payload.get("subject") if payload.get("subject") is not None else row["subject"]),str(payload.get("invoice_date") if payload.get("invoice_date") is not None else row["invoice_date"]),str(payload.get("due_date") if payload.get("due_date") is not None else row["due_date"]),str(payload.get("customer_reference") if payload.get("customer_reference") is not None else row["customer_reference"]),str(payload.get("notes") if payload.get("notes") is not None else row["notes"]),totals["net"],totals["tax"],totals["gross"],_now(),invoice_id))
        return {"ok":True,"item":_finance_invoice_dict(conn,conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone(),True)}


@router.post("/finance/invoices/{invoice_id}/finalize", dependencies=auth)
async def finance_invoice_finalize(invoice_id: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Rechnung nicht gefunden.")
        if row["direction"]=="customer" and row["status"]=="draft":
            now=_now(); final_no=_business_next_no(conn,"customer_invoice","RE")
            conn.execute("UPDATE finance_invoices SET invoice_no=?,status='open',finalized_at=?,updated_at=? WHERE id=?",(final_no,now,now,invoice_id))
        return {"ok":True,"item":_finance_invoice_dict(conn,conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone(),True)}


@router.get("/finance/invoices/{invoice_id}/file", dependencies=auth)
async def finance_invoice_file(invoice_id: str) -> Response:
    with _db() as conn:
        row=conn.execute("SELECT file_path,file_name,file_mime FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row or not row["file_path"]: raise HTTPException(status_code=404,detail="Keine Belegdatei vorhanden.")
        path=Path(str(row["file_path"])); name=str(row["file_name"] or path.name); mime=str(row["file_mime"] or mimetypes.guess_type(name)[0] or "application/octet-stream")
    if not path.exists(): raise HTTPException(status_code=404,detail="Belegdatei wurde nicht gefunden.")
    return FileResponse(path,media_type=mime,filename=name)


@router.get("/finance/orders/{sales_order_id}/invoices", dependencies=auth)
async def finance_order_invoices(sales_order_id: str) -> dict[str, Any]:
    with _db() as conn:
        rows=conn.execute("SELECT * FROM finance_invoices WHERE sales_order_id=? ORDER BY created_at DESC",(sales_order_id,)).fetchall()
        return {"ok":True,"items":[_finance_invoice_dict(conn,r,False) for r in rows]}


@router.get("/finance/lexware/settings", dependencies=auth)
async def finance_lexware_settings_get() -> dict[str, Any]:
    return {"ok":True,**_lexware_public_settings()}


@router.put("/finance/lexware/settings", dependencies=auth)
async def finance_lexware_settings_put(request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    if str(os.getenv("LEXWARE_API_TOKEN","") or "").strip() and payload.get("token"):
        raise HTTPException(status_code=409,detail="Der Lexware-Schlüssel wird über die Server-Umgebung verwaltet und kann hier nicht überschrieben werden.")
    _lexware_settings_save(payload)
    return {"ok":True,**_lexware_public_settings()}


@router.post("/finance/lexware/test", dependencies=auth)
async def finance_lexware_test() -> dict[str, Any]:
    try:
        data=await asyncio.to_thread(_lexware_request,"/v1/posting-categories","GET",None,"application/json",30)
        cats=data.get("content") if isinstance(data,dict) and isinstance(data.get("content"),list) else (data if isinstance(data,list) else [])
        return {"ok":True,"configured":True,"category_count":len(cats),"message":"Lexware Office ist erreichbar."}
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc


@router.get("/finance/lexware/posting-categories", dependencies=auth)
async def finance_lexware_categories() -> dict[str, Any]:
    try:
        data=await asyncio.to_thread(_lexware_request,"/v1/posting-categories","GET",None,"application/json",30)
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc
    cats=data.get("content") if isinstance(data,dict) and isinstance(data.get("content"),list) else (data if isinstance(data,list) else [])
    return {"ok":True,"items":[{"id":str(x.get("id") or ""),"name":str(x.get("name") or ""),"type":str(x.get("type") or "")} for x in cats if isinstance(x,dict)]}


@router.post("/finance/lexware/sync", dependencies=auth)
async def finance_lexware_sync() -> dict[str, Any]:
    try:
        result=await asyncio.to_thread(_lexware_sync_vouchers_blocking)
        return {"ok":True,**result}
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc


def _finance_lexware_payload(conn: sqlite3.Connection, row: sqlite3.Row, settings: dict[str, Any]) -> dict[str, Any]:
    direction=str(row["direction"] or "customer")
    category_id=str(settings.get("sales_category_id") if direction=="customer" else settings.get("purchase_category_id") or "").strip()
    if not category_id:
        label="Einnahmen-/Verkaufskategorie" if direction=="customer" else "Ausgabenkategorie"
        raise RuntimeError(f"Bitte in den Lexware-Einstellungen zuerst eine {label} auswählen.")
    grouped: dict[float,dict[str,float]]={}
    if direction=="supplier":
        rate=float(row["tax_rate"] or 19); grouped[rate]={"gross":float(row["total_gross"] or 0),"tax":float(row["total_tax"] or 0)}
    else:
        for item in conn.execute("SELECT * FROM finance_invoice_items WHERE invoice_id=?",(row["id"],)).fetchall():
            rate=float(item["tax_rate"] or 0); g=grouped.setdefault(rate,{"gross":0.0,"tax":0.0}); g["gross"]+=float(item["gross_total"] or 0); g["tax"]+=float(item["tax_total"] or 0)
        if not grouped:
            rate=float(row["tax_rate"] or 19); grouped[rate]={"gross":float(row["total_gross"] or 0),"tax":float(row["total_tax"] or 0)}
    voucher_items=[{"amount":round(v["gross"],2),"taxAmount":round(v["tax"],2),"taxRatePercent":rate,"categoryId":category_id} for rate,v in grouped.items()]
    number=str(row["invoice_no"] if direction=="customer" else (row["external_invoice_no"] or row["invoice_no"]))
    remark_parts=[f"HCA {row['invoice_no']}"]
    if row["sales_order_id"]: remark_parts.append(f"Auftrag {row['sales_order_id']}")
    if row["customer_name"]: remark_parts.append(str(row["customer_name"]))
    if row["supplier_name"]: remark_parts.append(str(row["supplier_name"]))
    return {"type":"salesinvoice" if direction=="customer" else "purchaseinvoice","voucherNumber":number,"voucherDate":str(row["invoice_date"] or _finance_today()),"dueDate":str(row["due_date"] or row["invoice_date"] or _finance_today()),"totalGrossAmount":round(float(row["total_gross"] or 0),2),"totalTaxAmount":round(float(row["total_tax"] or 0),2),"taxType":"gross","useCollectiveContact":True,"remark":" · ".join(remark_parts),"voucherItems":voucher_items}


@router.post("/finance/invoices/{invoice_id}/lexware-legacy", dependencies=auth)
async def finance_invoice_to_lexware(invoice_id: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Rechnung nicht gefunden.")
        if row["direction"]=="customer" and row["status"]=="draft": raise HTTPException(status_code=409,detail="Bitte die Kundenrechnung zuerst festschreiben.")
        if row["lexware_voucher_id"]: return {"ok":True,"item":_finance_invoice_dict(conn,row,True),"already_exists":True}
        settings=_lexware_settings_load(); payload=_finance_lexware_payload(conn,row,settings); file_info=(str(row["file_path"] or ""),str(row["file_name"] or ""),str(row["file_mime"] or ""))
    try:
        created=await asyncio.to_thread(_lexware_request,"/v1/vouchers","POST",payload,"application/json",45)
        vid=str(created.get("id") or "") if isinstance(created,dict) else ""
        if not vid: raise RuntimeError("Lexware hat keine Beleg-ID zurückgegeben.")
        if file_info[0]: await asyncio.to_thread(_lexware_upload_file,vid,*file_info)
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc
    now=_now(); vt=str(payload.get("type") or "")
    with _db() as conn:
        conn.execute("UPDATE finance_invoices SET lexware_voucher_id=?,lexware_voucher_type=?,lexware_status='open',lexware_open_amount=?,lexware_deeplink=?,lexware_synced_at=?,updated_at=? WHERE id=?",(vid,vt,float(row["total_gross"] or 0),_finance_deeplink(vt,vid),now,now,invoice_id))
        updated=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        return {"ok":True,"item":_finance_invoice_dict(conn,updated,True)}


# ---------------------------------------------------------------------------
# HCA v0.10.3 · Shoppreise, Veredelungskalkulation und Angebotsmail
# ---------------------------------------------------------------------------
def _mail_settings() -> dict[str, Any]:
    try:
        d=json.loads(MAIL_SETTINGS_FILE.read_text(encoding="utf-8")) if MAIL_SETTINGS_FILE.exists() else {}
        return d if isinstance(d,dict) else {}
    except Exception: return {}

def _save_mail_settings(d: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    MAIL_SETTINGS_FILE.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    try: os.chmod(MAIL_SETTINGS_FILE,0o600)
    except Exception: pass


def _document_settings() -> dict[str, str]:
    data = dict(DOCUMENT_DEFAULTS)
    with _db() as conn:
        row = conn.execute("SELECT value_json FROM shared_settings WHERE setting_key=?", (DOCUMENT_SETTINGS_KEY,)).fetchone()
    stored = _loads(row["value_json"], {}) if row else {}
    if isinstance(stored, dict):
        for key in DOCUMENT_DEFAULTS:
            if key in stored:
                data[key] = str(stored.get(key) or "").strip()
    return data


@router.get("/business/document-settings", dependencies=auth)
async def business_document_settings_get() -> dict[str, Any]:
    return {"ok": True, "settings": _document_settings()}


@router.put("/business/document-settings", dependencies=auth)
async def business_document_settings_put(request: Request) -> dict[str, Any]:
    body = await request.json()
    values = {key: str((body if isinstance(body, dict) else {}).get(key) or "").strip() for key in DOCUMENT_DEFAULTS}
    if not values["company_name"] or not values["street"] or not values["postal_code"] or not values["city"]:
        raise HTTPException(status_code=400, detail="Firmenname und vollständige Anschrift sind erforderlich.")
    if values["email"] and "@" not in values["email"]:
        raise HTTPException(status_code=400, detail="Die E-Mail-Adresse ist ungültig.")
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO shared_settings(setting_key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(setting_key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            (DOCUMENT_SETTINGS_KEY, _json(values), now),
        )
    return {"ok": True, "settings": values}

def _woo_form_post(path: str, fields: dict[str, Any], timeout: int=35) -> Any:
    base_url=str(os.getenv("WC_URL","") or "").strip().rstrip("/")
    if not base_url: raise RuntimeError("WooCommerce ist nicht konfiguriert.")
    data=urllib.parse.urlencode({k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in fields.items()}).encode()
    req=urllib.request.Request(base_url+path,data=data,headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"HCA-Manager/0.10.3"},method="POST")
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def _shop_configuration_from_hca(raw: dict[str, Any]) -> dict[str, Any]:
    cfg=raw.get("config") if isinstance(raw.get("config"),dict) else {}
    steps=cfg.get("production_steps") if isinstance(cfg.get("production_steps"),list) else []
    positions=[]
    for i,s in enumerate(steps):
        if not isinstance(s,dict): continue
        if bool(s.get("manual_override")): continue
        did=int(s.get("druckart_id") or 0); cost=int(s.get("cost_id") or 0); bearb=int(s.get("bearbeitung_cost_id") or 0)
        positions.append({"posNumber":i+1,"areaIndex":int(s.get("area_index") or i),"areaId":str(s.get("area_id") or ""),"areaName":str(s.get("position") or s.get("area_name") or ""),"druckartId":did,"druckartLabel":str(s.get("technique_label") or s.get("technique") or ""),"colorsCount":max(1,int(s.get("colors_count") or 1)),"costId":cost,"bearbeitungCostId":bearb})
    return {"color":cfg.get("color") or "","positions":positions}

@router.post("/business/shop-price", dependencies=auth)
async def business_shop_price(request: Request) -> dict[str, Any]:
    body=await request.json(); pid=int(body.get("product_id") or 0); qty=max(1,int(body.get("quantity") or 1))
    if not pid: raise HTTPException(status_code=400,detail="Produkt-ID fehlt.")
    configuration=body.get("configuration") if isinstance(body.get("configuration"),dict) else _shop_configuration_from_hca(body)
    # Wenn keine Veredelung gewählt ist, liefert der Wizard trotzdem den mengenabhängigen Artikelpreis.
    try:
        d=await asyncio.to_thread(_woo_form_post,"/?wc-ajax=wsk_wak_calculate_price",{"product_id":pid,"qty":qty,"configuration":configuration})
        if not isinstance(d,dict) or not d.get("success"):
            raise RuntimeError(str((d or {}).get("data") or "Shopkalkulation fehlgeschlagen"))
        x=d.get("data") or {}
        return {"ok":True,"product_id":pid,"qty":qty,"base_unit":round(float(x.get("base") or 0),4),"unit_netto":round(float(x.get("unit_netto") or 0),4),"article_total":round(float(x.get("article_total") or 0),2),"print_total":round(float(x.get("print_total") or 0),2),"setup_total":round(float(x.get("setup_total") or 0),2),"setup_discount_total":round(float(x.get("setup_discount_total") or 0),2),"handling_total":round(float(x.get("bearbeitung_total") or 0),2),"normal_total":round(float(x.get("normal_total") or x.get("total_netto") or 0),2),"total_netto":round(float(x.get("total_netto") or 0),2),"positions":x.get("positions") or [],"bundle_applied":x.get("bundle_applied"),"bundle_suggestion":x.get("bundle_suggestion"),"source":"woocommerce-wizard"}
    except Exception as exc:
        # Sicherer Fallback auf den WooCommerce-Produktpreis, falls ein Produkt den WSK-Rechner nicht nutzt.
        try:
            p=await asyncio.to_thread(_woo_json,f"/products/{pid}")
            price=float((p or {}).get("price") or 0)
            return {"ok":True,"product_id":pid,"qty":qty,"base_unit":price,"unit_netto":price,"article_total":round(price*qty,2),"print_total":0,"setup_total":0,"handling_total":0,"total_netto":round(price*qty,2),"positions":[],"source":"woocommerce-product","warning":str(exc)}
        except Exception as exc2: raise HTTPException(status_code=502,detail=f"Shoppreis konnte nicht geladen werden: {exc2}")

@router.get("/mail/settings", dependencies=auth)
async def get_mail_settings() -> dict[str, Any]:
    d=_mail_settings(); return {"ok":True,"settings":{k:v for k,v in d.items() if k!="password"},"password_set":bool(d.get("password"))}

@router.put("/mail/settings", dependencies=auth)
async def put_mail_settings(request: Request) -> dict[str, Any]:
    body=await request.json(); old=_mail_settings();
    if not str(body.get("password") or "").strip() and old.get("password"): body["password"]=old["password"]
    _save_mail_settings({"host":str(body.get("host") or "").strip(),"port":int(body.get("port") or 587),"username":str(body.get("username") or "").strip(),"password":str(body.get("password") or ""),"from_email":str(body.get("from_email") or "").strip(),"from_name":str(body.get("from_name") or "HCA Manager").strip(),"security":str(body.get("security") or "starttls")})
    return {"ok":True}

def _send_smtp(to_email:str,subject:str,html:str,text:str="",attachments: list[tuple[str,str,bytes]] | None=None) -> None:
    s=_mail_settings(); host=str(s.get("host") or ""); port=int(s.get("port") or 587)
    if not host:
        accounts=_mail_accounts() if "_mail_accounts" in globals() else []
        account=next((x for x in accounts if x.get("is_default")),accounts[0] if accounts else None)
        if account:
            s={"host":account.get("smtp_host"),"port":account.get("smtp_port"),"username":account.get("username") or account.get("email"),"password":account.get("smtp_password") or account.get("imap_password"),"from_email":account.get("email"),"from_name":account.get("from_name"),"security":account.get("smtp_security"),"reply_to":account.get("reply_to")}
            host=str(s.get("host") or "");port=int(s.get("port") or 587)
    if not host: raise RuntimeError("SMTP ist noch nicht eingerichtet.")
    msg=EmailMessage(); msg["Subject"]=subject; msg["From"]=f'{s.get("from_name") or "HCA Manager"} <{s.get("from_email") or s.get("username") or ""}>'; msg["To"]=to_email
    if s.get("reply_to"): msg["Reply-To"]=str(s.get("reply_to"))
    msg.set_content(text or re.sub(r"<[^>]+>"," ",html)); msg.add_alternative(html,subtype="html")
    for filename,mime,raw in attachments or []:
        main,sub=(str(mime or "application/octet-stream").split("/",1)+["octet-stream"])[:2]
        msg.add_attachment(raw,maintype=main,subtype=sub,filename=str(filename or "Anhang"))
    if str(s.get("security") or "starttls")=="ssl": smtp=smtplib.SMTP_SSL(host,port,timeout=30)
    else:
        smtp=smtplib.SMTP(host,port,timeout=30); smtp.ehlo()
        if str(s.get("security") or "starttls")=="starttls": smtp.starttls(); smtp.ehlo()
    try:
        if s.get("username"): smtp.login(str(s.get("username")),str(s.get("password") or ""))
        smtp.send_message(msg)
    finally: smtp.quit()

@router.post("/sales/quotes/{quote_id}/email", dependencies=auth)
async def email_quote(quote_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); to=str(body.get("to") or "").strip(); subject=str(body.get("subject") or "").strip(); message=str(body.get("message") or "").strip()
    if not to or "@" not in to: raise HTTPException(status_code=400,detail="Empfänger-E-Mail fehlt.")
    with _db() as conn:
        q=conn.execute("SELECT q.*,c.company_name,c.first_name,c.last_name FROM sales_quotes q LEFT JOIN crm_customers c ON c.id=q.customer_id WHERE q.id=?",(quote_id,)).fetchone()
        if not q: raise HTTPException(status_code=404,detail="Angebot nicht gefunden.")
        items=conn.execute("SELECT * FROM sales_quote_items WHERE quote_id=? ORDER BY position_no",(quote_id,)).fetchall()
        customer=conn.execute("SELECT * FROM crm_customers WHERE id=?",(q["customer_id"],)).fetchone()
        billing,_=_business_customer_snapshot(conn,customer,str(q["contact_id"] or ""),str(q["billing_address_id"] or ""),str(q["shipping_address_id"] or ""))
        quote=_business_quote_dict(conn,q,True)
    rows="".join(f"<tr><td style='padding:8px;border-bottom:1px solid #ddd'>{i+1}</td><td style='padding:8px;border-bottom:1px solid #ddd'>{str(r['description'] or '')}</td><td style='padding:8px;border-bottom:1px solid #ddd;text-align:right'>{float(r['quantity'] or 0):g}</td><td style='padding:8px;border-bottom:1px solid #ddd;text-align:right'>{float(r['unit_price'] or 0):.2f} €</td></tr>" for i,r in enumerate(items))
    html=f"<div style='font-family:Arial,sans-serif;max-width:760px'><div style='border-top:5px solid #e75303;padding-top:18px'><h2>{q['quote_no'] or 'Angebot'} · {q['subject'] or ''}</h2><p>{message}</p><table style='width:100%;border-collapse:collapse'><tr><th>Pos.</th><th>Beschreibung</th><th>Menge</th><th>Einzel netto</th></tr>{rows}</table><p style='margin-top:24px'>Freundliche Grüße<br>Werbestudio Königswinter</p></div></div>"
    pdf=_commercial_pdf_bytes("quote",quote,billing); filename=f"Angebot_{q['quote_no'] or quote_id}.pdf"
    try: await asyncio.to_thread(_send_smtp,to,subject or f"Angebot {q['quote_no'] or ''}",html,message,[(filename,"application/pdf",pdf)])
    except Exception as exc: raise HTTPException(status_code=502,detail=f"E-Mail konnte nicht gesendet werden: {exc}")
    with _db() as conn: conn.execute("UPDATE sales_quotes SET status=CASE WHEN status IN ('draft','ready') THEN 'sent' ELSE status END,updated_at=? WHERE id=?",(_now(),quote_id)); conn.commit()
    return {"ok":True,"to":to}

@router.post("/sales/orders", dependencies=auth)
async def sales_order_create_direct(request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    customer_id=str(payload.get("customer_id") or "")
    with _db() as conn:
        customer=conn.execute("SELECT * FROM crm_customers WHERE id=?",(customer_id,)).fetchone()
        if not customer: raise HTTPException(status_code=400,detail="Kunde nicht gefunden.")
        oid=str(uuid.uuid4()); ono=_business_next_no(conn,"sales_order","AU"); now=_now()
        billing,shipping=_business_customer_snapshot(conn,customer,str(payload.get("contact_id") or ""),str(payload.get("billing_address_id") or ""),str(payload.get("shipping_address_id") or ""))
        conn.execute("INSERT INTO sales_orders(id,order_no,source_quote_id,customer_id,customer_name,contact_id,subject,status,due_date,customer_reference,billing_json,shipping_json,internal_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(oid,ono,"",customer_id,_business_customer_name(customer),str(payload.get("contact_id") or ""),str(payload.get("subject") or "Auftrag"),"confirmed",str(payload.get("due_date") or ""),str(payload.get("customer_reference") or ""),_json(billing),_json(shipping),str(payload.get("internal_note") or ""),now,now))
        _business_replace_items(conn,"sales_order_items","sales_order_id",oid,payload.get("items") or [])
        row=conn.execute("SELECT * FROM sales_orders WHERE id=?",(oid,)).fetchone()
        return {"ok":True,"item":_business_order_dict(conn,row)}

@router.post("/mail/test", dependencies=auth)
async def test_mail_settings(request: Request) -> dict[str, Any]:
    body=await request.json(); to=str(body.get("to") or "").strip()
    if not to: to=str(_mail_settings().get("from_email") or _mail_settings().get("username") or "")
    if not to or "@" not in to: raise HTTPException(status_code=400,detail="Bitte zuerst eine gültige Absender-E-Mail speichern.")
    try: await asyncio.to_thread(_send_smtp,to,"HCA Manager · E-Mail-Test","<p>Die E-Mail-Verbindung des HCA Managers funktioniert.</p>","Die E-Mail-Verbindung des HCA Managers funktioniert.")
    except Exception as exc: raise HTTPException(status_code=502,detail=f"E-Mail-Test fehlgeschlagen: {exc}")
    return {"ok":True,"to":to}


# ---------------------------------------------------------------------------
# HCA v0.11.5 · Lieferscheine, Teillieferungen und Tracking
# ---------------------------------------------------------------------------

DELIVERY_NOTE_STATUSES = {"ready", "shipped", "cancelled"}


def _delivery_qty(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0)), 3)
    except Exception:
        return 0.0


def _delivery_variant_key(color: str = "", size: str = "") -> str:
    return f"{str(color or '').strip()}|{str(size or '').strip()}"


def _delivery_already_delivered(conn: sqlite3.Connection, source_item_id: str, variant_key: str) -> float:
    row = conn.execute(
        """SELECT COALESCE(SUM(i.quantity),0) AS qty
           FROM delivery_note_items i JOIN delivery_notes n ON n.id=i.delivery_note_id
           WHERE i.source_item_id=? AND i.variant_key=? AND n.status<>'cancelled'""",
        (str(source_item_id or ""), str(variant_key or "")),
    ).fetchone()
    return _delivery_qty(row["qty"] if row else 0)


def _delivery_order_candidates(conn: sqlite3.Connection, sales_order_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM sales_order_items WHERE sales_order_id=? ORDER BY position_no,id",
        (sales_order_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row["item_type"] or "product").lower() == "service":
            continue
        cfg = _loads(row["config_json"], {})
        if not isinstance(cfg, dict):
            cfg = {}
        color = str(cfg.get("color") or "").strip()
        sizes = cfg.get("sizes") if isinstance(cfg.get("sizes"), dict) else {}
        size_skus = cfg.get("size_skus") if isinstance(cfg.get("size_skus"), dict) else {}
        variants: list[tuple[str, float, str]] = []
        if sizes:
            for size, raw_qty in sizes.items():
                qty = _delivery_qty(raw_qty)
                if qty > 0:
                    variants.append((str(size), qty, str(size_skus.get(size) or row["sku"] or "")))
        else:
            variants.append((str(cfg.get("size") or ""), _delivery_qty(row["quantity"] or 1), str(row["sku"] or "")))
        for size, total, sku in variants:
            variant_key = _delivery_variant_key(color, size)
            delivered = _delivery_already_delivered(conn, str(row["id"]), variant_key)
            remaining = max(0.0, round(total - delivered, 3))
            out.append({
                "candidate_key": f"{row['id']}::{variant_key}", "source_item_id": str(row["id"]),
                "variant_key": variant_key, "position_no": int(row["position_no"] or 0),
                "sku": sku, "description": str(row["description"] or ""), "color": color, "size": size,
                "quantity": total, "already_delivered": delivered, "remaining_quantity": remaining,
                "unit": str(row["unit"] or "Stk."),
            })
    return out


def _delivery_invoice_candidates(conn: sqlite3.Connection, invoice_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM finance_invoice_items WHERE invoice_id=? ORDER BY position_no,id", (invoice_id,)
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        description = str(row["description"] or "").strip()
        if not description or re.match(r"^(Einrichtung|Druckvorbereitung)\b", description, re.I):
            continue
        source_item_id = str(row["source_item_id"] or f"invoice:{row['id']}")
        variant_key = ""
        total = _delivery_qty(row["quantity"] or 1)
        delivered = _delivery_already_delivered(conn, source_item_id, variant_key)
        out.append({
            "candidate_key": f"{source_item_id}::{variant_key}", "source_item_id": source_item_id,
            "variant_key": variant_key, "position_no": int(row["position_no"] or 0),
            "sku": str(row["sku"] or ""), "description": description, "color": "", "size": "",
            "quantity": total, "already_delivered": delivered,
            "remaining_quantity": max(0.0, round(total - delivered, 3)), "unit": str(row["unit"] or "Stk."),
        })
    return out


def _delivery_source(conn: sqlite3.Connection, source_type: str, source_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_type = str(source_type or "").lower()
    if source_type == "order":
        row = conn.execute("SELECT * FROM sales_orders WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Auftrag nicht gefunden.")
        source = {
            "source_type": "order", "source_id": source_id, "sales_order_id": source_id, "invoice_id": "",
            "customer_id": str(row["customer_id"] or ""), "customer_name": str(row["customer_name"] or ""),
            "order_no": str(row["order_no"] or ""), "invoice_no": "",
            "shipping": _loads(row["shipping_json"], {}), "recipient_email": "",
        }
        source["recipient_email"] = str((source["shipping"] or {}).get("email") or "")
        return source, _delivery_order_candidates(conn, source_id)
    if source_type == "invoice":
        row = conn.execute("SELECT * FROM finance_invoices WHERE id=?", (source_id,)).fetchone()
        if not row or str(row["direction"] or "") != "customer":
            raise HTTPException(status_code=404, detail="Kundenrechnung nicht gefunden.")
        source = {
            "source_type": "invoice", "source_id": source_id,
            "sales_order_id": str(row["sales_order_id"] or ""), "invoice_id": source_id,
            "customer_id": str(row["customer_id"] or ""), "customer_name": str(row["customer_name"] or ""),
            "order_no": "", "invoice_no": str(row["invoice_no"] or ""),
            "shipping": _loads(row["shipping_json"], {}), "recipient_email": "",
        }
        if source["sales_order_id"]:
            order = conn.execute("SELECT order_no FROM sales_orders WHERE id=?", (source["sales_order_id"],)).fetchone()
            source["order_no"] = str(order["order_no"] or "") if order else ""
        source["recipient_email"] = str((source["shipping"] or {}).get("email") or "")
        return source, _delivery_invoice_candidates(conn, source_id)
    raise HTTPException(status_code=400, detail="Quelle muss Auftrag oder Rechnung sein.")


def _delivery_note_dict(conn: sqlite3.Connection, row: sqlite3.Row, include_items: bool = True) -> dict[str, Any]:
    d = dict(row)
    d["shipping"] = _loads(d.pop("shipping_json", "{}"), {})
    if include_items:
        d["items"] = [dict(x) for x in conn.execute(
            "SELECT * FROM delivery_note_items WHERE delivery_note_id=? ORDER BY position_no,id", (row["id"],)
        ).fetchall()]
    d["item_count"] = int(conn.execute(
        "SELECT COUNT(*) FROM delivery_note_items WHERE delivery_note_id=?", (row["id"],)
    ).fetchone()[0])
    return d


def _delivery_selected_items(candidates: list[dict[str, Any]], requested: Any) -> list[dict[str, Any]]:
    lookup = {str(x["candidate_key"]): x for x in candidates}
    selected: list[dict[str, Any]] = []
    if isinstance(requested, list) and requested:
        for raw in requested:
            if not isinstance(raw, dict):
                continue
            candidate = lookup.get(str(raw.get("candidate_key") or ""))
            if not candidate:
                raise HTTPException(status_code=400, detail="Eine ausgewählte Position gehört nicht zur Quelle.")
            qty = _delivery_qty(raw.get("quantity"))
            if qty <= 0:
                continue
            if qty > _delivery_qty(candidate["remaining_quantity"]) + 0.0001:
                raise HTTPException(status_code=409, detail=f"Für „{candidate['description']}“ sind nur noch {candidate['remaining_quantity']:g} lieferbar.")
            selected.append({**candidate, "quantity": qty})
    else:
        selected = [{**x, "quantity": _delivery_qty(x["remaining_quantity"])} for x in candidates if _delivery_qty(x["remaining_quantity"]) > 0]
    if not selected:
        raise HTTPException(status_code=400, detail="Bitte mindestens einen noch nicht gelieferten Artikel auswählen.")
    return selected


def _delivery_insert(conn: sqlite3.Connection, source: dict[str, Any], items: list[dict[str, Any]], *,
                     shipment_id: str = "", tracking_number: str = "", tracking_url: str = "",
                     carrier_name: str = "", notes: str = "") -> dict[str, Any]:
    did = str(uuid.uuid4()); now = _now(); number = _business_next_no(conn, "delivery_note", "LS")
    status = "shipped" if tracking_number or tracking_url else "ready"
    conn.execute(
        """INSERT INTO delivery_notes(id,delivery_note_no,source_type,source_id,sales_order_id,invoice_id,shipment_id,
           customer_id,customer_name,order_no,invoice_no,delivery_date,status,shipping_json,recipient_email,
           carrier_name,tracking_number,tracking_url,notes,printed_at,email_sent_at,email_error,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (did, number, str(source.get("source_type") or "order"), str(source.get("source_id") or ""),
         str(source.get("sales_order_id") or ""), str(source.get("invoice_id") or ""), str(shipment_id or ""),
         str(source.get("customer_id") or ""), str(source.get("customer_name") or ""), str(source.get("order_no") or ""),
         str(source.get("invoice_no") or ""), _finance_today(), status, _json(source.get("shipping") or {}),
         str(source.get("recipient_email") or ""), str(carrier_name or ""), str(tracking_number or ""),
         str(tracking_url or ""), str(notes or ""), "", "", "", now, now),
    )
    pos = 10
    for raw in items:
        conn.execute(
            """INSERT INTO delivery_note_items(id,delivery_note_id,position_no,source_item_id,variant_key,sku,
               description,color,size,quantity,unit,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), did, int(raw.get("position_no") or pos), str(raw.get("source_item_id") or ""),
             str(raw.get("variant_key") or ""), str(raw.get("sku") or ""), str(raw.get("description") or ""),
             str(raw.get("color") or ""), str(raw.get("size") or ""), _delivery_qty(raw.get("quantity")),
             str(raw.get("unit") or "Stk."), now, now),
        )
        pos += 10
    return _delivery_note_dict(conn, conn.execute("SELECT * FROM delivery_notes WHERE id=?", (did,)).fetchone(), True)


def _delivery_pdf_escape(value: Any) -> str:
    text = str(value or "").encode("cp1252", "replace").decode("cp1252")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _delivery_wrap(value: Any, width: int = 82) -> list[str]:
    words = str(value or "").split(); lines: list[str] = []; current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    return lines or [""]


def _letterhead_footer_commands(page_no: int) -> list[str]:
    settings = _document_settings()
    commands = ["0.25 0.25 0.25 rg"]

    def put(text: Any, x: float, y: float, size: float = 6.5, bold: bool = False, white: bool = False) -> None:
        if not str(text or "").strip():
            return
        commands.append("1 1 1 rg" if white else "0.25 0.25 0.25 rg")
        commands.append(f"BT /{'F2' if bold else 'F1'} {size:g} Tf 1 0 0 1 {x:g} {y:g} Tm ({_delivery_pdf_escape(text)}) Tj ET")

    if page_no == 1:
        sender = " · ".join(x for x in [settings["company_name"], settings["street"], f'{settings["postal_code"]} {settings["city"]}'.strip()] if x)
        put(sender, 71, 699, 6.5)

    put(settings["street"], 52, 44, 6.4)
    put(f'{settings["postal_code"]} {settings["city"]}'.strip(), 52, 35, 6.4)
    put(f'Tel. {settings["phone"]}' if settings["phone"] else "", 52, 26, 6.4)
    put(settings["email"], 52, 17, 6.4)

    put(settings["account_holder"], 235, 57, 6.4, True)
    put(settings["bank_name"], 235, 47, 6.4)
    put(f'IBAN {settings["iban"]}' if settings["iban"] else "", 235, 37, 6.4)
    put(f'BIC {settings["bic"]}' if settings["bic"] else "", 235, 27, 6.4)
    put(f'USt-IdNr. {settings["vat_id"]}' if settings["vat_id"] else "", 235, 17, 6.4)
    put(settings["website"], 421, 35, 7.4, True, True)
    commands.append("0 0 0 rg")
    return commands


def _letterhead_pdf(page_contents: list[bytes]) -> bytes:
    asset_dir = Path(__file__).resolve().parent / "assets"
    first_image = (asset_dir / "briefpapier-seite1.jpg").read_bytes()
    continuation_image = (asset_dir / "briefpapier-seite2.jpg").read_bytes()
    count = len(page_contents)
    font_regular = 5 + count * 2
    font_bold = font_regular + 1
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: ("<< /Type /Pages /Kids [" + " ".join(f"{5+i*2} 0 R" for i in range(count)) + f"] /Count {count} >>").encode(),
        3: f"<< /Type /XObject /Subtype /Image /Width 2480 /Height 3508 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(first_image)} >>\nstream\n".encode() + first_image + b"\nendstream",
        4: f"<< /Type /XObject /Subtype /Image /Width 2480 /Height 3508 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(continuation_image)} >>\nstream\n".encode() + continuation_image + b"\nendstream",
        font_regular: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        font_bold: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    }
    for i, body in enumerate(page_contents):
        page_id = 5 + i * 2
        content_id = page_id + 1
        image_id = 3 if i == 0 else 4
        prefix = f"q 595.276 0 0 841.89 0 0 cm /BG Do Q\n".encode()
        footer = ("\n".join(_letterhead_footer_commands(i + 1)) + "\n").encode("cp1252", "replace")
        content = prefix + footer + body
        objects[page_id] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.276 841.89] /Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> /XObject << /BG {image_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        objects[content_id] = f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id in range(1, font_bold + 1):
        offsets.append(len(result)); result.extend(f"{obj_id} 0 obj\n".encode()); result.extend(objects[obj_id]); result.extend(b"\nendobj\n")
    xref = len(result); result.extend(f"xref\n0 {font_bold+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {font_bold+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


def _delivery_pdf_bytes(note: dict[str, Any]) -> bytes:
    address = note.get("shipping") if isinstance(note.get("shipping"), dict) else {}
    address_lines = [address.get("name"), address.get("attention"), address.get("street"),
                     " ".join(x for x in [str(address.get("zip") or ""), str(address.get("city") or "")] if x),
                     address.get("country")]
    item_lines: list[str] = []
    for index, item in enumerate(note.get("items") or [], 1):
        details = " · ".join(x for x in [str(item.get("color") or ""), str(item.get("size") or "")] if x)
        prefix = f"{index:>2}   {_delivery_qty(item.get('quantity')):g} {item.get('unit') or 'Stk.'}   {item.get('sku') or '-'}   "
        text = str(item.get("description") or "") + (f" ({details})" if details else "")
        wrapped = _delivery_wrap(prefix + text, 92)
        item_lines.extend(wrapped)
    chunks = [item_lines[i:i + 28] for i in range(0, len(item_lines), 28)] or [[]]
    page_contents: list[bytes] = []
    for page_no, chunk in enumerate(chunks, 1):
        commands = ["0 0 0 rg"]
        def put(text: Any, x: int, y: int, size: int = 10, bold: bool = False) -> None:
            font = "F2" if bold else "F1"
            commands.append(f"BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({_delivery_pdf_escape(text)}) Tj ET")
        put("LIEFERSCHEIN", 420, 684, 16, True)
        put(str(note.get("delivery_note_no") or ""), 420, 665, 10, True)
        if page_no == 1:
            y = 665
            for line in address_lines:
                if str(line or "").strip(): put(line, 46, y, 10); y -= 15
            put(f"Datum: {_document_date(note.get('delivery_date'))}", 360, 640, 10)
            if note.get("order_no"): put(f"Auftrag: {note.get('order_no')}", 360, 624, 10)
            if note.get("invoice_no"): put(f"Rechnung: {note.get('invoice_no')}", 360, 608, 10)
            if note.get("tracking_number"): put(f"Sendungsnummer: {note.get('tracking_number')}", 46, 574, 10, True)
            if note.get("tracking_url"): put(f"Sendungsverfolgung: {note.get('tracking_url')}", 46, 558, 8)
            table_y = 526
        else:
            put("Fortsetzung", 46, 650, 10, True)
            table_y = 625
        put("Pos.  Menge       Artikelnummer   Beschreibung", 46, table_y, 10, True)
        commands.append(f"0.75 0.75 0.75 RG 46 {table_y-7:g} 503 0.8 re f 0 0 0 rg")
        y = table_y - 24
        for line in chunk:
            put(line, 46, y, 9); y -= 14
        if page_no == len(chunks):
            put("Die Lieferung enthält die oben aufgeführten Waren.", 46, max(92, y - 22), 9)
        put(f"Seite {page_no} von {len(chunks)}", 490, 88, 7)
        page_contents.append("\n".join(commands).encode("cp1252", "replace"))
    return _letterhead_pdf(page_contents)


def _document_date(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        return datetime.fromisoformat(raw[:10]).strftime("%d.%m.%Y")
    except Exception:
        return raw


def _document_money(value: Any) -> str:
    try:
        return f"{float(value or 0):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00 EUR"


def _commercial_pdf_bytes(kind: str, document: dict[str, Any], address: dict[str, Any]) -> bytes:
    is_quote = kind == "quote"
    is_order = kind == "order"
    title = "ANGEBOT" if is_quote else ("AUFTRAGSBESTÄTIGUNG" if is_order else "RECHNUNG")
    number = str(document.get("quote_no") if is_quote else (document.get("order_no") if is_order else document.get("invoice_no")) or "")
    date_value = str(document.get("created_at") if (is_quote or is_order) else document.get("invoice_date") or "")
    due_label = "Gültig bis" if is_quote else ("Liefertermin" if is_order else "Fällig am")
    due_value = str(document.get("valid_until") if is_quote else (document.get("due_date") if is_order else document.get("due_date")) or "")
    items = document.get("items") if isinstance(document.get("items"), list) else []
    rows: list[dict[str, Any]] = []
    position_no = 0
    for item in items:
        item_type = str(item.get("item_type") or "product").strip().lower()
        is_optional = item_type == "optional"
        if item_type == "text":
            position_no += 1
            rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(str(item.get("description") or ""), 82),
                         "quantity": 0, "unit": "", "unit_price": 0, "net_total": 0, "text": True, "optional": False})
            continue
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        details = []
        if config.get("color"): details.append(f"Farbe: {config['color']}")
        sizes = config.get("sizes") if isinstance(config.get("sizes"), dict) else {}
        selected_sizes = " · ".join(f"{key}: {float(value or 0):g}" for key, value in sizes.items() if float(value or 0) > 0)
        if selected_sizes: details.append("Größen: " + selected_sizes)
        if config.get("manufacturer"): details.append(f"Hersteller: {config['manufacturer']}")
        if config.get("weight"): details.append(f"Gewicht: {config['weight']} kg")
        dimensions = config.get("dimensions") if isinstance(config.get("dimensions"), dict) else {}
        dimensions_text = " × ".join(str(dimensions.get(key) or "").strip() for key in ("length", "width", "height") if str(dimensions.get(key) or "").strip())
        if dimensions_text: details.append(f"Maße: {dimensions_text} cm")
        description = str(item.get("description") or "")
        if details: description += " · " + " · ".join(details)
        if is_optional:
            option_net, _, option_gross = _business_line_amounts(item)
            description = f"OPTIONALE POSITION · Netto ({_document_money(option_net)}) · Brutto ({_document_money(option_gross)}) · " + description
        wrapped = _delivery_wrap(description, 47)
        quantity = float(item.get("quantity") or 0)
        unit_price = float(item.get("unit_price") or 0)
        discount_factor = 1.0 - max(0.0, min(100.0, float(item.get("discount_pct") or 0))) / 100.0
        position_no += 1
        rows.append({"index": position_no, "sku": str(item.get("sku") or ""), "lines": wrapped, "quantity": quantity,
                     "unit": str(item.get("unit") or "Stk."), "unit_price": unit_price * discount_factor, "net_total": quantity * unit_price * discount_factor,
                     "text": False, "optional": is_optional})

        steps = config.get("production_steps") if isinstance(config.get("production_steps"), list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            technique = str(step.get("technique_label") or step.get("technique") or "Veredelung").strip()
            if technique.lower() == "array":
                technique = ""
                wizard = config.get("wizard_config") if isinstance(config.get("wizard_config"), dict) else {}
                for wizard_area in wizard.get("areas", []) if isinstance(wizard.get("areas"), list) else []:
                    assignments = wizard_area.get("assignments", []) if isinstance(wizard_area, dict) else []
                    for assignment in assignments if isinstance(assignments, list) else []:
                        if isinstance(assignment, dict) and int(assignment.get("druckart_id") or 0) == int(step.get("druckart_id") or 0):
                            method = assignment.get("method") if isinstance(assignment.get("method"), dict) else {}
                            technique = str(method.get("name") or method.get("label") or "").strip()
                            break
                    if technique:
                        break
                technique = technique or str(step.get("technique_name") or step.get("technique") or "Veredelung").strip()
            area = str(step.get("position") or step.get("area_name") or "").strip()
            colors = max(0, int(step.get("colors_count") or 0))
            motif = str(step.get("motif") or "").strip()
            refinement_details = [x for x in [f"Position: {area}" if area else "", f"{colors}-farbig" if colors else "", f"Motiv: {motif}" if motif else ""] if x]
            print_unit = float(step.get("print_price") if step.get("print_price") is not None else step.get("unit_price") or 0)
            handling_unit = float(step.get("handling_price") or 0)
            # Legacy documents stored print and handling combined in unit_price.
            if step.get("print_price") is None and handling_unit > 0:
                print_unit = max(0.0, float(step.get("unit_price") or 0) - handling_unit)
            if print_unit > 0 or technique or area:
                position_no += 1
                label = technique + (" · " + " · ".join(refinement_details) if refinement_details else "")
                rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(label, 47), "quantity": quantity,
                             "unit": "Stk.", "unit_price": print_unit * discount_factor, "net_total": quantity * print_unit * discount_factor,
                             "text": False, "optional": is_optional})
            setup_total = float(step.get("setup_price") or 0)
            if setup_total > 0:
                position_no += 1
                setup_label = str(step.get("setup_label") or "").strip()
                if not setup_label.lower().startswith("einrichtungskosten"):
                    setup_label = "Einrichtungskosten" + (f" {setup_label}" if setup_label else "")
                if area: setup_label += f" · {area}"
                if float(step.get("setup_discount") or 0) > 0:
                    setup_label += f" · inkl. {float(step.get('setup_discount_percent') or 0):g} % Nachlass"
                rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(setup_label, 47), "quantity": 1,
                             "unit": "Pausch.", "unit_price": setup_total, "net_total": setup_total,
                             "text": False, "optional": is_optional})
            if handling_unit > 0:
                position_no += 1
                handling_label = "Bearbeitungskosten/Artikel"
                if area: handling_label += f" · {area}"
                rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(handling_label, 47), "quantity": quantity,
                             "unit": "Stk.", "unit_price": handling_unit * discount_factor, "net_total": quantity * handling_unit * discount_factor,
                             "text": False, "optional": is_optional})

    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []; used = 0.0
    for row in rows:
        height = 24.0 + max(0, len(row["lines"]) - 1) * 11.0 + (11.0 if row["sku"] else 0.0)
        if current and used + height > 295:
            pages.append(current); current = []; used = 0.0
        current.append(row); used += height
    pages.append(current)

    totals = document.get("totals") if isinstance(document.get("totals"), dict) else {}
    total_net = float(totals.get("net") if (is_quote or is_order) else document.get("total_net") or 0)
    total_tax = float(totals.get("tax") if (is_quote or is_order) else document.get("total_tax") or 0)
    total_gross = float(totals.get("gross") if (is_quote or is_order) else document.get("total_gross") or 0)
    page_contents: list[bytes] = []
    for page_index, page_rows in enumerate(pages, 1):
        commands = ["0 0 0 rg"]
        def put(text: Any, x: float, y: float, size: float = 9, bold: bool = False) -> None:
            commands.append(f"BT /{'F2' if bold else 'F1'} {size:g} Tf 1 0 0 1 {x:g} {y:g} Tm ({_delivery_pdf_escape(text)}) Tj ET")
        def draw_line(x1: float, y1: float, x2: float, y2: float, width: float = 0.45) -> None:
            commands.append(f"0.52 0.52 0.52 RG {width:g} w {x1:g} {y1:g} m {x2:g} {y2:g} l S 0 0 0 rg")

        put(title, 420, 684, 16, True)
        put(number or "Entwurf", 420, 665, 10, True)
        y = 665
        if page_index == 1:
            for line in [address.get("name"), address.get("attention"), address.get("street"),
                         " ".join(x for x in [str(address.get("zip") or ""), str(address.get("city") or "")] if x),
                         address.get("country")]:
                if str(line or "").strip(): put(line, 46, y, 10); y -= 15
            meta_x = 420 if is_quote else 360
            put(f"Datum: {_document_date(date_value)}", meta_x, 640, 9)
            if due_value: put(f"{due_label}: {_document_date(due_value)}", meta_x, 624, 9)
            if document.get("customer_reference"): put(f"Ihre Referenz: {document.get('customer_reference')}", meta_x, 608, 9)
            if document.get("subject"): put(document.get("subject"), 46, 574, 12, True)
            intro = str(document.get("intro_text") or "") if is_quote else ""
            if intro:
                intro_lines = _delivery_wrap(intro, 92)[:3]
                iy = 555
                for line in intro_lines: put(line, 46, iy, 8.5); iy -= 12
            table_y = 515 if intro else 540
        else:
            put("Fortsetzung", 46, 650, 10, True)
            table_y = 625
        commands.append(f"0.95 0.95 0.93 rg 46 {table_y-9:g} 503 23 re f 0 0 0 rg")
        put("Pos.", 50, table_y, 7.5, True); put("Bezeichnung", 79, table_y, 7.5, True)
        put("Menge", 348, table_y, 7.5, True); put("Einheit", 392, table_y, 7.5, True); put("Einzel netto", 433, table_y, 7.5, True); put("Gesamt netto", 490, table_y, 7.5, True)
        table_top = table_y + 14; header_bottom = table_y - 9
        draw_line(46,table_top,549,table_top,0.7); draw_line(46,header_bottom,549,header_bottom,0.7)
        for x in (46,75,345,390,430,487,549): draw_line(x,table_top,x,header_bottom,0.55)
        row_top = header_bottom
        for row in page_rows:
            row_height = 24.0 + max(0, len(row["lines"]) - 1) * 11.0 + (11.0 if row["sku"] else 0.0)
            row_bottom = row_top - row_height
            y = row_top - 17
            if row["index"] % 2 == 0:
                commands.append(f"0.985 0.985 0.975 rg 46 {row_bottom:g} 503 {row_height:g} re f 0 0 0 rg")
            put(row["index"], 51, y, 8.2)
            put(row["lines"][0], 80, y, 8.5, True)
            if not row.get("text"):
                put(f'{row["quantity"]:g}', 350, y, 8.5)
                put(row["unit"], 394, y, 8.5)
                unit_price_text = _document_money(row["unit_price"])
                net_total_text = _document_money(row["net_total"])
                if row.get("optional"):
                    unit_price_text = f"({unit_price_text})"
                    net_total_text = f"({net_total_text})"
                put(unit_price_text, 434, y, 7.7)
                put(net_total_text, 491, y, 7.7, True)
            y -= 12
            for line in row["lines"][1:]: put(line, 80, y, 7.8); y -= 11
            if row["sku"]: put(f'Art.-Nr. {row["sku"]}', 80, y, 7); y -= 11
            draw_line(46,row_bottom,549,row_bottom,0.4)
            for x in (46,75,345,390,430,487,549): draw_line(x,row_top,x,row_bottom,0.4)
            row_top = row_bottom
        y = row_top
        if page_index == len(pages):
            totals_top = y
            totals_y = totals_top - 18
            totals_bottom = totals_top - 66
            draw_line(46,totals_top,549,totals_top,0.7); draw_line(46,totals_bottom,549,totals_bottom,0.7); draw_line(46,totals_top,46,totals_bottom,0.7); draw_line(487,totals_top,487,totals_bottom,0.55); draw_line(549,totals_top,549,totals_bottom,0.7)
            put("Zwischensumme (netto)", 55, totals_y, 8.7); put(_document_money(total_net), 491, totals_y, 8.7, True)
            put("Umsatzsteuer", 55, totals_y - 17, 8.7); put(_document_money(total_tax), 491, totals_y - 17, 8.7, True)
            put("Gesamtbetrag", 55, totals_y - 39, 10, True); put(_document_money(total_gross), 491, totals_y - 39, 10, True)
            closing = str(document.get("footer_text") or document.get("notes") or "").strip()
            if closing:
                cy = totals_bottom - 18
                for line in _delivery_wrap(closing, 82)[:3]: put(line, 46, cy, 8); cy -= 11
            payment_text = str(document.get("payment_term_text") or "").strip()
            if payment_text:
                cy = max(94, totals_bottom - 64)
                for line in _delivery_wrap("Zahlungsbedingung: " + payment_text, 82)[:3]: put(line, 46, cy, 8); cy -= 11
        put(f"Seite {page_index} von {len(pages)}", 490, 88, 7)
        page_contents.append("\n".join(commands).encode("cp1252", "replace"))
    return _letterhead_pdf(page_contents)


@router.post("/sales/quotes/preview", dependencies=auth)
async def sales_quote_preview(request: Request) -> Response:
    """Render the current editor payload without saving a quote or allocating a number."""
    payload = await request.json()
    payload = payload if isinstance(payload, dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    address: dict[str, Any] = {}
    customer_id = str(payload.get("customer_id") or "")
    payment_text = str(payload.get("payment_term_text") or "")
    with _db() as conn:
        customer = conn.execute("SELECT * FROM crm_customers WHERE id=?", (customer_id,)).fetchone() if customer_id else None
        if customer:
            address, _ = _business_customer_snapshot(
                conn, customer, str(payload.get("contact_id") or ""),
                str(payload.get("billing_address_id") or ""), str(payload.get("shipping_address_id") or "")
            )
        if not payment_text:
            payment_text = str(_payment_term_for_customer(conn, customer_id, str(payload.get("payment_term_id") or "")).get("text") or "")
    now = _now()
    document = {
        **payload,
        "quote_no": "VORSCHAU",
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "items": items,
        "totals": _business_totals(items),
        "payment_term_text": payment_text,
    }
    return Response(_commercial_pdf_bytes("quote", document, address), media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="Angebot_Vorschau.pdf"'})


@router.get("/sales/quotes/{quote_id}/pdf", dependencies=auth)
async def sales_quote_pdf(quote_id: str) -> Response:
    with _db() as conn:
        row = conn.execute("SELECT * FROM sales_quotes WHERE id=?", (quote_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Angebot nicht gefunden.")
        quote = _business_quote_dict(conn, row, True)
        customer = conn.execute("SELECT * FROM crm_customers WHERE id=?", (row["customer_id"],)).fetchone()
        billing, _ = _business_customer_snapshot(conn, customer, str(row["contact_id"] or ""), str(row["billing_address_id"] or ""), str(row["shipping_address_id"] or ""))
    filename = f"Angebot_{quote.get('quote_no') or quote_id}.pdf"
    return Response(_commercial_pdf_bytes("quote", quote, billing), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/finance/invoices/{invoice_id}/pdf", dependencies=auth)
async def finance_invoice_pdf(invoice_id: str) -> Response:
    with _db() as conn:
        row = conn.execute("SELECT * FROM finance_invoices WHERE id=? AND direction='customer'", (invoice_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Kundenrechnung nicht gefunden.")
        invoice = _finance_invoice_dict(conn, row, True)
    filename = f"Rechnung_{invoice.get('invoice_no') or invoice_id}.pdf"
    return Response(_commercial_pdf_bytes("invoice", invoice, invoice.get("billing") or {}), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/sales/orders/{sales_order_id}/pdf", dependencies=auth)
async def sales_order_pdf(sales_order_id: str) -> Response:
    with _db() as conn:
        row=conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        order=_business_order_dict(conn,row,True)
    filename=f"Auftrag_{order.get('order_no') or sales_order_id}.pdf"
    return Response(_commercial_pdf_bytes("order",order,order.get("billing") or {}),media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{filename}"'})


def _delivery_send_email_blocking(delivery_note_id: str, to_email: str = "") -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM delivery_notes WHERE id=?", (delivery_note_id,)).fetchone()
        if not row: raise RuntimeError("Lieferschein nicht gefunden.")
        note = _delivery_note_dict(conn, row, True)
    to_email = str(to_email or note.get("recipient_email") or (note.get("shipping") or {}).get("email") or "").strip()
    if not to_email or "@" not in to_email: raise RuntimeError("Beim Kunden ist keine gültige E-Mail-Adresse hinterlegt.")
    tracking = str(note.get("tracking_number") or "").strip(); link = str(note.get("tracking_url") or "").strip()
    track_html = ""
    if tracking: track_html += f"<p><b>Sendungsnummer:</b> {html_lib.escape(tracking)}</p>"
    if link: track_html += f"<p><a href='{html_lib.escape(link, quote=True)}'>Sendung verfolgen</a></p>"
    rows = "".join(
        f"<tr><td style='padding:7px;border-bottom:1px solid #ddd'>{i+1}</td>"
        f"<td style='padding:7px;border-bottom:1px solid #ddd'>{html_lib.escape(str(x.get('description') or ''))}</td>"
        f"<td style='padding:7px;border-bottom:1px solid #ddd'>{html_lib.escape(' · '.join(v for v in [str(x.get('color') or ''),str(x.get('size') or '')] if v))}</td>"
        f"<td style='padding:7px;border-bottom:1px solid #ddd;text-align:right'>{_delivery_qty(x.get('quantity')):g} {html_lib.escape(str(x.get('unit') or 'Stk.'))}</td></tr>"
        for i, x in enumerate(note.get("items") or [])
    )
    html = f"""<div style='font-family:Arial,sans-serif;max-width:760px;border-top:5px solid #e75303;padding-top:18px'>
      <h2>Lieferschein {html_lib.escape(str(note.get('delivery_note_no') or ''))}</h2>
      <p>Guten Tag,</p><p>Ihre Lieferung wurde zusammengestellt bzw. versendet. Den Lieferschein finden Sie als PDF im Anhang.</p>
      {track_html}<table style='width:100%;border-collapse:collapse;margin-top:20px'><tr><th>Pos.</th><th>Artikel</th><th>Farbe / Größe</th><th>Menge</th></tr>{rows}</table>
      <p style='margin-top:24px'>Freundliche Grüße<br>Werbestudio Königswinter</p></div>"""
    pdf = _delivery_pdf_bytes(note); filename = f"Lieferschein_{note.get('delivery_note_no') or delivery_note_id}.pdf"
    _send_smtp(to_email, f"Lieferschein {note.get('delivery_note_no') or ''} · Werbestudio Königswinter", html,
               f"Ihr Lieferschein {note.get('delivery_note_no') or ''}. Sendungsnummer: {tracking}",
               [(filename, "application/pdf", pdf)])
    with _db() as conn:
        conn.execute("UPDATE delivery_notes SET recipient_email=?,email_sent_at=?,email_error='',updated_at=? WHERE id=?",
                     (to_email, _now(), _now(), delivery_note_id))
    return {"ok": True, "to": to_email}


async def _delivery_try_auto_email(delivery_note_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_delivery_send_email_blocking, delivery_note_id, "")
    except Exception as exc:
        with _db() as conn:
            conn.execute("UPDATE delivery_notes SET email_error=?,updated_at=? WHERE id=?", (str(exc), _now(), delivery_note_id))
        return {"ok": False, "error": str(exc)}


def _delivery_address_from_shipment(shipment: dict[str, Any]) -> dict[str, Any]:
    recipient = shipment.get("recipient") if isinstance(shipment.get("recipient"), dict) else {}
    street = " ".join(x for x in [str(recipient.get("address_line_1") or "").strip(), str(recipient.get("house_number") or "").strip()] if x)
    return {"name": str(recipient.get("company") or recipient.get("recipient_name") or ""),
            "attention": str(recipient.get("recipient_name") or ""), "street": street,
            "zip": str(recipient.get("postal_code") or ""), "city": str(recipient.get("city") or ""),
            "country": str(recipient.get("country_code") or "DE"), "email": str(recipient.get("email") or ""),
            "phone": str(recipient.get("phone") or "")}


def _delivery_task_items(shipment: dict[str, Any]) -> list[dict[str, Any]]:
    try: tasks = _all_tasks()
    except Exception: tasks = []
    relevant = [t for t in tasks if str(t.get("order_id") or "") == str(shipment.get("order_id") or "")]
    if str(shipment.get("mode") or "") == "merch":
        relevant = [t for t in relevant if str(t.get("shipping_group") or "") == str(shipment.get("shipment_key") or "")]
    grouped: dict[tuple[str,str,str,str], float] = {}
    for task in relevant:
        key = (str(task.get("article") or task.get("description") or "Artikel"), str(task.get("sku") or ""),
               str(task.get("color") or ""), str(task.get("size") or ""))
        grouped[key] = max(grouped.get(key, 0), _delivery_qty(task.get("target_qty") or task.get("quantity") or 1))
    return [{"candidate_key": f"task::{i}", "source_item_id": "", "variant_key": _delivery_variant_key(k[2],k[3]),
             "position_no": (i+1)*10, "description": k[0], "sku": k[1], "color": k[2], "size": k[3],
             "quantity": qty, "remaining_quantity": qty, "unit": "Stk."}
            for i,(k,qty) in enumerate(grouped.items()) if qty > 0]


def _delivery_from_shipment_blocking(shipment_id: str) -> dict[str, Any]:
    shipment = _shipment_by_id(shipment_id)
    with _db() as conn:
        existing = conn.execute("SELECT * FROM delivery_notes WHERE shipment_id=?", (shipment_id,)).fetchone()
        if existing:
            conn.execute("UPDATE delivery_notes SET carrier_name=?,tracking_number=?,tracking_url=?,status='shipped',updated_at=? WHERE id=?",
                         (str(shipment.get("carrier_name") or ""), str(shipment.get("tracking_number") or ""),
                          str(shipment.get("tracking_url") or ""), _now(), existing["id"]))
            return _delivery_note_dict(conn, conn.execute("SELECT * FROM delivery_notes WHERE id=?", (existing["id"],)).fetchone(), True)
        link = conn.execute("SELECT * FROM production_order_links WHERE base_order_id=? ORDER BY created_at DESC LIMIT 1", (str(shipment.get("order_id") or ""),)).fetchone()
        sales_order_id = str(link["sales_order_id"] or "") if link else ""
        source: dict[str, Any]; items: list[dict[str, Any]]
        if sales_order_id:
            source, candidates = _delivery_source(conn, "order", sales_order_id)
            task_items = _delivery_task_items(shipment)
            if task_items:
                selected=[]
                for task_item in task_items:
                    match = next((x for x in candidates if _delivery_qty(x.get("remaining_quantity")) > 0 and
                                  ((task_item["sku"] and x["sku"] == task_item["sku"]) or x["description"].strip().lower() == task_item["description"].strip().lower()) and
                                  (not task_item["color"] or x["color"].strip().lower() == task_item["color"].strip().lower()) and
                                  (not task_item["size"] or x["size"] == task_item["size"])), None)
                    if match:
                        selected.append({**match, "quantity": min(_delivery_qty(match.get("remaining_quantity")), _delivery_qty(task_item["quantity"]))})
                    else:
                        selected.append({**task_item, "quantity": _delivery_qty(task_item["quantity"])})
                items = selected or [{**x,"quantity":x["remaining_quantity"]} for x in candidates if _delivery_qty(x["remaining_quantity"]) > 0]
            else:
                items = [{**x, "quantity": x["remaining_quantity"]} for x in candidates if _delivery_qty(x["remaining_quantity"]) > 0]
        else:
            address = _delivery_address_from_shipment(shipment); task_items = _delivery_task_items(shipment)
            source = {"source_type":"shipment", "source_id":shipment_id, "sales_order_id":"", "invoice_id":"",
                      "customer_id":"", "customer_name":str(shipment.get("customer") or address.get("name") or ""),
                      "order_no":str(shipment.get("order_no") or shipment.get("order_id") or ""), "invoice_no":"",
                      "shipping":address, "recipient_email":str(address.get("email") or "")}
            items = task_items
        if not items:
            items = [{"description": str(shipment.get("name") or "Lieferung"), "quantity": max(1,_delivery_qty(shipment.get("target_qty") or 1)), "unit":"Stk.", "sku":"", "color":"", "size":"", "source_item_id":"", "variant_key":""}]
        source["source_type"] = "shipment"; source["source_id"] = shipment_id
        source["shipping"] = _delivery_address_from_shipment(shipment) or source.get("shipping") or {}
        source["recipient_email"] = str((source["shipping"] or {}).get("email") or source.get("recipient_email") or "")
        return _delivery_insert(conn, source, items, shipment_id=shipment_id,
                                tracking_number=str(shipment.get("tracking_number") or ""),
                                tracking_url=str(shipment.get("tracking_url") or ""),
                                carrier_name=str(shipment.get("carrier_name") or ""))


def _delivery_recipient(note: dict[str, Any]) -> dict[str, Any]:
    address = note.get("shipping") if isinstance(note.get("shipping"), dict) else {}
    street, house = _split_street_house(str(address.get("street") or ""), "")
    return {"recipient_name":str(address.get("attention") or address.get("name") or note.get("customer_name") or ""),
            "company":str(address.get("name") or note.get("customer_name") or ""), "address_line_1":street,
            "house_number":house, "address_line_2":"", "postal_code":str(address.get("zip") or ""),
            "city":str(address.get("city") or ""), "country_code":_country_code(address.get("country") or "DE"),
            "email":str(note.get("recipient_email") or address.get("email") or ""), "phone":str(address.get("phone") or "")}


def _delivery_ensure_shipment(delivery_note_id: str, parcel: dict[str, Any] | None = None) -> dict[str, Any]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM delivery_notes WHERE id=?", (delivery_note_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Lieferschein nicht gefunden.")
        note = _delivery_note_dict(conn, row, True)
        if note.get("shipment_id"):
            existing = conn.execute("SELECT * FROM shipments WHERE id=?", (note["shipment_id"],)).fetchone()
            if existing:
                if parcel is not None: conn.execute("UPDATE shipments SET parcel_json=?,updated_at=? WHERE id=?", (_json(_clean_parcel(parcel)),_now(),note["shipment_id"]))
                return _shipment_row(conn.execute("SELECT * FROM shipments WHERE id=?", (note["shipment_id"],)).fetchone())
        recipient = _delivery_recipient(note); _validate_recipient(recipient)
        sid = str(uuid.uuid4()); now = _now(); clean = _clean_parcel(parcel or {})
        conn.execute("INSERT INTO shipments(id,order_id,shipment_key,mode,name,recipient_json,parcel_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (sid, str(note.get("sales_order_id") or delivery_note_id), f"DELIVERY:{note['delivery_note_no']}", "business",
                      str(note["delivery_note_no"]), _json(recipient), _json(clean), "ready", now, now))
        conn.execute("UPDATE delivery_notes SET shipment_id=?,updated_at=? WHERE id=?", (sid, now, delivery_note_id))
        return _shipment_by_id(sid)


@router.get("/delivery-notes", dependencies=auth)
async def delivery_notes(q: str = "", sales_order_id: str = "", invoice_id: str = "", shipment_id: str = "", limit: int = 1000) -> dict[str, Any]:
    sql="SELECT * FROM delivery_notes WHERE 1=1"; args: list[Any]=[]
    if sales_order_id: sql+=" AND sales_order_id=?"; args.append(str(sales_order_id))
    if invoice_id: sql+=" AND invoice_id=?"; args.append(str(invoice_id))
    if shipment_id: sql+=" AND shipment_id=?"; args.append(str(shipment_id))
    if str(q or "").strip():
        like=f"%{str(q).strip()}%"; sql+=" AND (delivery_note_no LIKE ? OR customer_name LIKE ? OR order_no LIKE ? OR invoice_no LIKE ? OR tracking_number LIKE ?)"; args.extend([like]*5)
    sql+=" ORDER BY delivery_date DESC,created_at DESC LIMIT ?"; args.append(max(1,min(int(limit or 1000),3000)))
    with _db() as conn:
        return {"ok":True,"items":[_delivery_note_dict(conn,r,False) for r in conn.execute(sql,args).fetchall()]}


@router.get("/delivery-notes/candidates/{source_type}/{source_id}", dependencies=auth)
async def delivery_note_candidates(source_type: str, source_id: str) -> dict[str, Any]:
    with _db() as conn:
        source, items = _delivery_source(conn, source_type, source_id)
        return {"ok":True,"source":source,"items":items}


@router.post("/delivery-notes/from-{source_type}/{source_id}", dependencies=auth)
async def delivery_note_create_from_source(source_type: str, source_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    with _db() as conn:
        source,candidates=_delivery_source(conn,source_type,source_id); selected=_delivery_selected_items(candidates,payload.get("items"))
        note=_delivery_insert(conn,source,selected,notes=str(payload.get("notes") or ""))
        if str(payload.get("status") or "") == "draft":
            conn.execute("UPDATE delivery_notes SET status='draft',updated_at=? WHERE id=?",(_now(),note["id"]))
            note=_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(note["id"],)).fetchone(),True)
        return {"ok":True,"item":note}


@router.post("/delivery-notes/from-shipment/{shipment_id}", dependencies=auth)
async def delivery_note_create_from_shipment(shipment_id: str) -> dict[str, Any]:
    note=await asyncio.to_thread(_delivery_from_shipment_blocking,shipment_id)
    email=await _delivery_try_auto_email(str(note["id"])) if not note.get("email_sent_at") else {"ok":True,"already_sent":True}
    with _db() as conn: fresh=_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(note["id"],)).fetchone(),True)
    return {"ok":True,"item":fresh,"email":email}


@router.get("/delivery-notes/{delivery_note_id}", dependencies=auth)
async def delivery_note_get(delivery_note_id: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        return {"ok":True,"item":_delivery_note_dict(conn,row,True)}


@router.put("/delivery-notes/{delivery_note_id}/tracking", dependencies=auth)
async def delivery_note_tracking(delivery_note_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    number=str(payload.get("tracking_number") or "").strip(); url=str(payload.get("tracking_url") or "").strip(); carrier=str(payload.get("carrier_name") or "").strip()
    if not number and not url: raise HTTPException(status_code=400,detail="Bitte Sendungsnummer oder vollständigen Sendungslink eintragen.")
    if url and not re.match(r"^https?://",url,re.I): raise HTTPException(status_code=400,detail="Der Sendungslink muss vollständig mit http:// oder https:// beginnen.")
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(): raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        conn.execute("UPDATE delivery_notes SET carrier_name=?,tracking_number=?,tracking_url=?,status='shipped',updated_at=? WHERE id=?",(carrier,number,url,_now(),delivery_note_id))
        return {"ok":True,"item":_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(),True)}


@router.post("/delivery-notes/{delivery_note_id}/printed", dependencies=auth)
async def delivery_note_printed(delivery_note_id: str) -> dict[str, Any]:
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(): raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        conn.execute("UPDATE delivery_notes SET printed_at=?,updated_at=? WHERE id=?",(_now(),_now(),delivery_note_id))
    return {"ok":True}


@router.get("/delivery-notes/{delivery_note_id}/pdf", dependencies=auth)
async def delivery_note_pdf(delivery_note_id: str) -> Response:
    with _db() as conn:
        row=conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        note=_delivery_note_dict(conn,row,True)
    raw=_delivery_pdf_bytes(note); filename=f"Lieferschein_{note['delivery_note_no']}.pdf"
    return Response(raw,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{filename}"'})


@router.post("/delivery-notes/{delivery_note_id}/email", dependencies=auth)
async def delivery_note_email(delivery_note_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    try: return await asyncio.to_thread(_delivery_send_email_blocking,delivery_note_id,str(payload.get("to") or ""))
    except Exception as exc: raise HTTPException(status_code=502,detail=f"Lieferschein konnte nicht per E-Mail gesendet werden: {exc}") from exc


@router.post("/delivery-notes/{delivery_note_id}/shipping-options", dependencies=auth)
async def delivery_note_shipping_options(delivery_note_id: str, request: Request) -> dict[str, Any]:
    payload=await request.json(); payload=payload if isinstance(payload,dict) else {}
    shipment=await asyncio.to_thread(_delivery_ensure_shipment,delivery_note_id,payload)
    try:
        parcel=await asyncio.to_thread(_save_parcel,shipment["id"],payload); items=await asyncio.to_thread(_shipping_options,shipment["recipient"],parcel)
        return {"ok":True,"items":items,"cheapest":items[0] if items and items[0].get("price_value") is not None else None}
    except Exception as exc: raise HTTPException(status_code=502,detail=str(exc)) from exc


@router.post("/delivery-notes/{delivery_note_id}/ship", dependencies=auth)
async def delivery_note_ship(delivery_note_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    shipment=await asyncio.to_thread(_delivery_ensure_shipment,delivery_note_id,body)
    option={"shipping_option_code":body.get("shipping_option_code") or body.get("code"),"contract_id":body.get("contract_id"),
            "name":body.get("shipping_name") or body.get("name") or "","carrier_name":body.get("carrier_name") or "",
            "price_value":body.get("price_value"),"price_currency":body.get("price_currency") or "EUR"}
    try: shipped=await asyncio.to_thread(_ship,shipment["id"],option,body)
    except Exception as exc: raise HTTPException(status_code=502,detail=str(exc)) from exc
    with _db() as conn:
        conn.execute("UPDATE delivery_notes SET carrier_name=?,tracking_number=?,tracking_url=?,status='shipped',updated_at=? WHERE id=?",
                     (str(shipped.get("carrier_name") or ""),str(shipped.get("tracking_number") or ""),str(shipped.get("tracking_url") or ""),_now(),delivery_note_id))
        note=_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(),True)
    email=await _delivery_try_auto_email(delivery_note_id)
    return {"ok":True,"item":note,"shipment":shipped,"tracking_number":shipped.get("tracking_number","") ,"label_url":f"/api/hca-shared/shipments/{shipment['id']}/label","email":email}


# ---------------------------------------------------------------------------
# HCA v0.12.0 · Belegketten, Zahlungsbedingungen, Vorlagen und E-Mail-Client
# ---------------------------------------------------------------------------

def _payment_term_for_customer(conn: sqlite3.Connection, customer_id: str = "", requested_id: str = "") -> dict[str, Any]:
    term_id = str(requested_id or "").strip()
    if not term_id and customer_id:
        row = conn.execute("SELECT payment_term_id FROM crm_customers WHERE id=?", (customer_id,)).fetchone()
        term_id = str(row["payment_term_id"] or "") if row else ""
    row = conn.execute("SELECT * FROM payment_terms WHERE id=? AND active=1", (term_id,)).fetchone() if term_id else None
    if not row:
        row = conn.execute("SELECT * FROM payment_terms WHERE active=1 ORDER BY is_default DESC,name LIMIT 1").fetchone()
    return dict(row) if row else {"id": "", "name": "", "days": 14, "text": "Zahlbar innerhalb von 14 Tagen ohne Abzug."}


@router.get("/business/payment-terms", dependencies=auth)
async def payment_terms_get() -> dict[str, Any]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM payment_terms WHERE active=1 ORDER BY is_default DESC,name").fetchall()
        return {"ok": True, "items": [dict(x) for x in rows]}


@router.put("/business/payment-terms", dependencies=auth)
async def payment_terms_put(request: Request) -> dict[str, Any]:
    body = await request.json(); body = body if isinstance(body, dict) else {}
    items = body.get("items") if isinstance(body.get("items"), list) else []
    if not items:
        raise HTTPException(status_code=400, detail="Mindestens eine Zahlungsbedingung ist erforderlich.")
    now = _now(); default_id = str(body.get("default_id") or "")
    with _db() as conn:
        seen: set[str] = set()
        for index, raw in enumerate(items):
            if not isinstance(raw, dict): continue
            pid = str(raw.get("id") or uuid.uuid4()); name = str(raw.get("name") or "").strip()
            if not name: continue
            days = max(0, min(3650, int(raw.get("days") or 0)))
            text = str(raw.get("text") or f"Zahlbar innerhalb von {days} Tagen ohne Abzug.").strip()
            is_default = 1 if pid == default_id or (not default_id and index == 0) else 0
            conn.execute("INSERT INTO payment_terms(id,name,days,text,is_default,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,days=excluded.days,text=excluded.text,is_default=excluded.is_default,active=1,updated_at=excluded.updated_at",
                         (pid,name,days,text,is_default,1,now,now)); seen.add(pid)
        if seen:
            marks = ",".join("?" for _ in seen)
            conn.execute(f"UPDATE payment_terms SET active=0,is_default=0,updated_at=? WHERE id NOT IN ({marks})", (now,*seen))
        rows = conn.execute("SELECT * FROM payment_terms WHERE active=1 ORDER BY is_default DESC,name").fetchall()
        return {"ok": True, "items": [dict(x) for x in rows]}


@router.put("/crm/customers/{customer_id}/payment-term", dependencies=auth)
async def customer_payment_term_put(customer_id: str, request: Request) -> dict[str, Any]:
    body = await request.json(); term_id = str((body if isinstance(body,dict) else {}).get("payment_term_id") or "")
    with _db() as conn:
        if term_id and not conn.execute("SELECT 1 FROM payment_terms WHERE id=? AND active=1", (term_id,)).fetchone():
            raise HTTPException(status_code=400, detail="Zahlungsbedingung nicht gefunden.")
        if not conn.execute("SELECT 1 FROM crm_customers WHERE id=?", (customer_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden.")
        conn.execute("UPDATE crm_customers SET payment_term_id=?,updated_at=? WHERE id=?", (term_id,_now(),customer_id))
        return {"ok": True, "payment_term_id": term_id}


@router.put("/documents/{doc_type}/{doc_id}/metadata", dependencies=auth)
async def document_metadata_put(doc_type: str, doc_id: str, request: Request) -> dict[str, Any]:
    body = await request.json(); body = body if isinstance(body,dict) else {}
    mapping = {"quote": ("sales_quotes", "customer_id"), "order": ("sales_orders", "customer_id"), "invoice": ("finance_invoices", "customer_id")}
    if doc_type not in mapping: raise HTTPException(status_code=400, detail="Unbekannter Belegtyp.")
    table, _ = mapping[doc_type]
    with _db() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (doc_id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Beleg nicht gefunden.")
        term = _payment_term_for_customer(conn, str(row["customer_id"] or ""), str(body.get("payment_term_id") or ""))
        sets = ["payment_term_id=?", "payment_term_text=?", "updated_at=?"]
        args: list[Any] = [term.get("id") or "", str(body.get("payment_term_text") or term.get("text") or ""), _now()]
        if doc_type == "quote": sets.append("source_channel=?"); args.append(str(body.get("source_channel") or "").strip())
        if "status" in body and str(body.get("status") or "") == "draft": sets.append("status='draft'")
        args.append(doc_id)
        conn.execute(f"UPDATE {table} SET {','.join(sets)} WHERE id=?", args)
        return {"ok": True, "payment_term": term}


def _document_relations(conn: sqlite3.Connection, doc_type: str, doc_id: str) -> list[dict[str, Any]]:
    quote_ids: set[str] = set(); order_ids: set[str] = set(); invoice_ids: set[str] = set(); delivery_ids: set[str] = set()
    if doc_type == "quote": quote_ids.add(doc_id)
    elif doc_type == "order": order_ids.add(doc_id)
    elif doc_type == "invoice": invoice_ids.add(doc_id)
    elif doc_type == "delivery": delivery_ids.add(doc_id)
    else: raise HTTPException(status_code=400, detail="Unbekannter Belegtyp.")
    if quote_ids:
        for qid in list(quote_ids):
            q = conn.execute("SELECT sales_order_id FROM sales_quotes WHERE id=?", (qid,)).fetchone()
            if q and q["sales_order_id"]: order_ids.add(str(q["sales_order_id"]))
            order_ids.update(str(x["id"]) for x in conn.execute("SELECT id FROM sales_orders WHERE source_quote_id=?", (qid,)).fetchall())
    if order_ids:
        marks=",".join("?" for _ in order_ids)
        quote_ids.update(str(x["source_quote_id"]) for x in conn.execute(f"SELECT source_quote_id FROM sales_orders WHERE id IN ({marks}) AND source_quote_id<>''", tuple(order_ids)).fetchall())
        invoice_ids.update(str(x["id"]) for x in conn.execute(f"SELECT id FROM finance_invoices WHERE sales_order_id IN ({marks})", tuple(order_ids)).fetchall())
        delivery_ids.update(str(x["id"]) for x in conn.execute(f"SELECT id FROM delivery_notes WHERE sales_order_id IN ({marks})", tuple(order_ids)).fetchall())
    if invoice_ids:
        marks=",".join("?" for _ in invoice_ids)
        rows=conn.execute(f"SELECT sales_order_id,source_quote_id FROM finance_invoices WHERE id IN ({marks})",tuple(invoice_ids)).fetchall()
        order_ids.update(str(x["sales_order_id"]) for x in rows if x["sales_order_id"])
        quote_ids.update(str(x["source_quote_id"]) for x in rows if x["source_quote_id"])
        delivery_ids.update(str(x["id"]) for x in conn.execute(f"SELECT id FROM delivery_notes WHERE invoice_id IN ({marks})",tuple(invoice_ids)).fetchall())
    if delivery_ids:
        marks=",".join("?" for _ in delivery_ids)
        rows=conn.execute(f"SELECT sales_order_id,invoice_id FROM delivery_notes WHERE id IN ({marks})",tuple(delivery_ids)).fetchall()
        order_ids.update(str(x["sales_order_id"]) for x in rows if x["sales_order_id"])
        invoice_ids.update(str(x["invoice_id"]) for x in rows if x["invoice_id"])
    # Zweiter Durchlauf: Startet die Suche bei Rechnung oder Lieferschein, wurden
    # Auftrag und Angebot erst in den vorherigen Blöcken bekannt.
    if order_ids:
        marks=",".join("?" for _ in order_ids)
        quote_ids.update(str(x["source_quote_id"]) for x in conn.execute(f"SELECT source_quote_id FROM sales_orders WHERE id IN ({marks}) AND source_quote_id<>''",tuple(order_ids)).fetchall())
        invoice_ids.update(str(x["id"]) for x in conn.execute(f"SELECT id FROM finance_invoices WHERE sales_order_id IN ({marks})",tuple(order_ids)).fetchall())
        delivery_ids.update(str(x["id"]) for x in conn.execute(f"SELECT id FROM delivery_notes WHERE sales_order_id IN ({marks})",tuple(order_ids)).fetchall())
    out=[]
    specs=[("quote",quote_ids,"sales_quotes","quote_no"),("order",order_ids,"sales_orders","order_no"),("invoice",invoice_ids,"finance_invoices","invoice_no"),("delivery",delivery_ids,"delivery_notes","delivery_note_no")]
    for kind, ids, table, number_col in specs:
        for rid in sorted(ids):
            if kind==doc_type and rid==doc_id: continue
            row=conn.execute(f"SELECT id,{number_col} AS number,status,updated_at FROM {table} WHERE id=?",(rid,)).fetchone()
            if row: out.append({"type":kind,"id":rid,"number":row["number"],"status":row["status"],"updated_at":row["updated_at"]})
    return sorted(out,key=lambda x:(x["type"],x["number"]))


@router.get("/documents/{doc_type}/{doc_id}/relations", dependencies=auth)
async def document_relations_get(doc_type: str, doc_id: str) -> dict[str, Any]:
    with _db() as conn: return {"ok":True,"items":_document_relations(conn,doc_type,doc_id)}


@router.post("/documents/{doc_type}/{doc_id}/duplicate", dependencies=auth)
async def document_duplicate(doc_type: str, doc_id: str) -> dict[str, Any]:
    now=_now()
    with _db() as conn:
        if doc_type=="quote":
            old=conn.execute("SELECT * FROM sales_quotes WHERE id=?",(doc_id,)).fetchone()
            if not old: raise HTTPException(status_code=404,detail="Angebot nicht gefunden.")
            nid=str(uuid.uuid4()); no=_business_next_no(conn,"quote","AN")
            conn.execute("INSERT INTO sales_quotes(id,quote_no,customer_id,customer_name,contact_id,subject,status,valid_until,currency,intro_text,footer_text,internal_note,sales_order_id,sent_at,accepted_at,created_at,updated_at,billing_address_id,shipping_address_id,source_channel,payment_term_id,payment_term_text,duplicated_from_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (nid,no,old["customer_id"],old["customer_name"],old["contact_id"],old["subject"],"draft",old["valid_until"],old["currency"],old["intro_text"],old["footer_text"],old["internal_note"],"","","",now,now,old["billing_address_id"],old["shipping_address_id"],old["source_channel"],old["payment_term_id"],old["payment_term_text"],doc_id))
            items=[_business_item_dict(x) for x in conn.execute("SELECT * FROM sales_quote_items WHERE quote_id=? ORDER BY position_no",(doc_id,)).fetchall()]
            _business_replace_items(conn,"sales_quote_items","quote_id",nid,items)
            return {"ok":True,"item":_business_quote_dict(conn,conn.execute("SELECT * FROM sales_quotes WHERE id=?",(nid,)).fetchone())}
        if doc_type=="order":
            old=conn.execute("SELECT * FROM sales_orders WHERE id=?",(doc_id,)).fetchone()
            if not old: raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
            nid=str(uuid.uuid4()); no=_business_next_no(conn,"sales_order","AU")
            conn.execute("INSERT INTO sales_orders(id,order_no,source_quote_id,customer_id,customer_name,contact_id,subject,status,due_date,customer_reference,billing_json,shipping_json,internal_note,created_at,updated_at,payment_term_id,payment_term_text,duplicated_from_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (nid,no,"",old["customer_id"],old["customer_name"],old["contact_id"],old["subject"],"draft",old["due_date"],old["customer_reference"],old["billing_json"],old["shipping_json"],old["internal_note"],now,now,old["payment_term_id"],old["payment_term_text"],doc_id))
            items=[_business_item_dict(x) for x in conn.execute("SELECT * FROM sales_order_items WHERE sales_order_id=? ORDER BY position_no",(doc_id,)).fetchall()]
            _business_replace_items(conn,"sales_order_items","sales_order_id",nid,items)
            return {"ok":True,"item":_business_order_dict(conn,conn.execute("SELECT * FROM sales_orders WHERE id=?",(nid,)).fetchone())}
        if doc_type=="invoice":
            old=conn.execute("SELECT * FROM finance_invoices WHERE id=? AND direction='customer'",(doc_id,)).fetchone()
            if not old: raise HTTPException(status_code=404,detail="Kundenrechnung nicht gefunden.")
            nid=str(uuid.uuid4()); no=f"DRAFT-{nid[:8].upper()}"
            conn.execute("INSERT INTO finance_invoices(id,invoice_no,direction,source,sales_order_id,customer_id,customer_name,supplier_name,external_invoice_no,subject,status,payment_status,invoice_date,due_date,currency,billing_json,shipping_json,customer_reference,purchase_reference,notes,total_net,total_tax,total_gross,tax_rate,created_at,updated_at,source_quote_id,payment_term_id,payment_term_text,duplicated_from_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (nid,no,"customer","hca","",old["customer_id"],old["customer_name"],"","",old["subject"],"draft","open",_finance_today(),old["due_date"],old["currency"],old["billing_json"],old["shipping_json"],old["customer_reference"],"",old["notes"],0,0,0,old["tax_rate"],now,now,"",old["payment_term_id"],old["payment_term_text"],doc_id))
            items=[dict(x) for x in conn.execute("SELECT * FROM finance_invoice_items WHERE invoice_id=? ORDER BY position_no",(doc_id,)).fetchall()]
            totals=_finance_replace_items(conn,nid,items); conn.execute("UPDATE finance_invoices SET total_net=?,total_tax=?,total_gross=? WHERE id=?",(totals["net"],totals["tax"],totals["gross"],nid))
            return {"ok":True,"item":_finance_invoice_dict(conn,conn.execute("SELECT * FROM finance_invoices WHERE id=?",(nid,)).fetchone(),True)}
        if doc_type=="delivery":
            old=conn.execute("SELECT * FROM delivery_notes WHERE id=?",(doc_id,)).fetchone()
            if not old: raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
            source={"source_type":"template","source_id":"","sales_order_id":"","invoice_id":"","customer_id":old["customer_id"],"customer_name":old["customer_name"],"order_no":"","invoice_no":"","shipping":_loads(old["shipping_json"],{}),"recipient_email":old["recipient_email"]}
            items=[dict(x) for x in conn.execute("SELECT * FROM delivery_note_items WHERE delivery_note_id=? ORDER BY position_no",(doc_id,)).fetchall()]
            note=_delivery_insert(conn,source,items,notes=old["notes"]); conn.execute("UPDATE delivery_notes SET status='draft',duplicated_from_id=? WHERE id=?",(doc_id,note["id"]))
            return {"ok":True,"item":_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(note["id"],)).fetchone(),True)}
    raise HTTPException(status_code=400,detail="Dieser Belegtyp kann nicht dupliziert werden.")


@router.put("/sales/orders/{sales_order_id}/draft", dependencies=auth)
async def sales_order_draft_update(sales_order_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    with _db() as conn:
        row=conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        if row["status"]!="draft": raise HTTPException(status_code=409,detail="Nur Auftragsentwürfe können bearbeitet werden.")
        customer_id=str(body.get("customer_id") or row["customer_id"]); customer=conn.execute("SELECT * FROM crm_customers WHERE id=?",(customer_id,)).fetchone()
        if not customer: raise HTTPException(status_code=400,detail="Kunde nicht gefunden.")
        billing,shipping=_business_customer_snapshot(conn,customer,str(body.get("contact_id") or row["contact_id"]),str(body.get("billing_address_id") or ""),str(body.get("shipping_address_id") or ""))
        conn.execute("UPDATE sales_orders SET customer_id=?,customer_name=?,contact_id=?,subject=?,due_date=?,customer_reference=?,billing_json=?,shipping_json=?,internal_note=?,updated_at=? WHERE id=?",
                     (customer_id,_business_customer_name(customer),str(body.get("contact_id") or ""),str(body.get("subject") or "Auftrag"),str(body.get("due_date") or ""),str(body.get("customer_reference") or ""),_json(billing),_json(shipping),str(body.get("internal_note") or ""),_now(),sales_order_id))
        _business_replace_items(conn,"sales_order_items","sales_order_id",sales_order_id,body.get("items") or [])
        return {"ok":True,"item":_business_order_dict(conn,conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone())}


@router.post("/sales/orders/{sales_order_id}/confirm", dependencies=auth)
async def sales_order_draft_confirm(sales_order_id: str) -> dict[str, Any]:
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone(): raise HTTPException(status_code=404,detail="Auftrag nicht gefunden.")
        conn.execute("UPDATE sales_orders SET status='confirmed',updated_at=? WHERE id=?",(_now(),sales_order_id))
        return {"ok":True,"item":_business_order_dict(conn,conn.execute("SELECT * FROM sales_orders WHERE id=?",(sales_order_id,)).fetchone())}


@router.put("/delivery-notes/{delivery_note_id}/draft", dependencies=auth)
async def delivery_note_draft_update(delivery_note_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    with _db() as conn:
        row=conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        if row["status"]!="draft": raise HTTPException(status_code=409,detail="Nur Lieferscheinentwürfe können bearbeitet werden.")
        items=body.get("items") if isinstance(body.get("items"),list) else []
        conn.execute("DELETE FROM delivery_note_items WHERE delivery_note_id=?",(delivery_note_id,)); now=_now()
        for i,x in enumerate(items):
            if not isinstance(x,dict) or not str(x.get("description") or "").strip():continue
            conn.execute("INSERT INTO delivery_note_items(id,delivery_note_id,position_no,source_item_id,variant_key,sku,description,color,size,quantity,unit,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (str(uuid.uuid4()),delivery_note_id,(i+1)*10,str(x.get("source_item_id") or ""),str(x.get("variant_key") or ""),str(x.get("sku") or ""),str(x.get("description") or ""),str(x.get("color") or ""),str(x.get("size") or ""),_delivery_qty(x.get("quantity") or 1),str(x.get("unit") or "Stk."),now,now))
        conn.execute("UPDATE delivery_notes SET notes=?,updated_at=? WHERE id=?",(str(body.get("notes") or ""),now,delivery_note_id))
        return {"ok":True,"item":_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(),True)}


@router.post("/delivery-notes/{delivery_note_id}/confirm", dependencies=auth)
async def delivery_note_draft_confirm(delivery_note_id: str) -> dict[str, Any]:
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(): raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        conn.execute("UPDATE delivery_notes SET status='ready',updated_at=? WHERE id=?",(_now(),delivery_note_id))
        return {"ok":True,"item":_delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone(),True)}


def _mail_accounts() -> list[dict[str, Any]]:
    try:
        data=json.loads(MAIL_ACCOUNTS_FILE.read_text(encoding="utf-8")) if MAIL_ACCOUNTS_FILE.exists() else []
        return data if isinstance(data,list) else []
    except Exception: return []


def _save_mail_accounts(items: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True,exist_ok=True); MAIL_ACCOUNTS_FILE.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")
    try: os.chmod(MAIL_ACCOUNTS_FILE,0o600)
    except Exception: pass


def _mail_public_account(a: dict[str, Any]) -> dict[str, Any]:
    return {k:v for k,v in a.items() if k not in {"imap_password","smtp_password"}} | {"password_set":bool(a.get("imap_password") or a.get("smtp_password"))}


def _decode_mail_header(value: str) -> str:
    parts=[]
    for raw, charset in decode_header(value or ""):
        parts.append(raw.decode(charset or "utf-8","replace") if isinstance(raw,bytes) else str(raw))
    return "".join(parts)


def _imap_connect(account: dict[str, Any]):
    host=str(account.get("imap_host") or ""); port=int(account.get("imap_port") or 993)
    if not host: raise RuntimeError("IMAP-Server fehlt.")
    client=imaplib.IMAP4_SSL(host,port,timeout=30) if str(account.get("imap_security") or "ssl")=="ssl" else imaplib.IMAP4(host,port,timeout=30)
    if str(account.get("imap_security") or "ssl")=="starttls": client.starttls()
    client.login(str(account.get("username") or account.get("email") or ""),str(account.get("imap_password") or "")); return client


@router.get("/mail/accounts", dependencies=auth)
async def mail_accounts_get() -> dict[str, Any]:
    return {"ok":True,"items":[_mail_public_account(x) for x in _mail_accounts()]}


@router.put("/mail/accounts", dependencies=auth)
async def mail_accounts_put(request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}; incoming=body.get("items") if isinstance(body.get("items"),list) else []
    old={str(x.get("id") or ""):x for x in _mail_accounts()}; out=[]
    for raw in incoming:
        if not isinstance(raw,dict): continue
        mid=str(raw.get("id") or uuid.uuid4()); previous=old.get(mid,{})
        item={"id":mid,"name":str(raw.get("name") or raw.get("email") or "Postfach").strip(),"email":str(raw.get("email") or "").strip(),"username":str(raw.get("username") or raw.get("email") or "").strip(),"imap_host":str(raw.get("imap_host") or "").strip(),"imap_port":int(raw.get("imap_port") or 993),"imap_security":str(raw.get("imap_security") or "ssl"),"smtp_host":str(raw.get("smtp_host") or "").strip(),"smtp_port":int(raw.get("smtp_port") or 587),"smtp_security":str(raw.get("smtp_security") or "starttls"),"from_name":str(raw.get("from_name") or "Werbestudio Königswinter").strip(),"reply_to":str(raw.get("reply_to") or "").strip(),"signature":str(raw.get("signature") or "").strip(),"is_default":bool(raw.get("is_default"))}
        item["imap_password"]=str(raw.get("imap_password") or previous.get("imap_password") or ""); item["smtp_password"]=str(raw.get("smtp_password") or previous.get("smtp_password") or item["imap_password"])
        out.append(item)
    if out and not any(x.get("is_default") for x in out): out[0]["is_default"]=True
    _save_mail_accounts(out); return {"ok":True,"items":[_mail_public_account(x) for x in out]}


def _mail_account(account_id: str) -> dict[str, Any]:
    account=next((x for x in _mail_accounts() if str(x.get("id"))==str(account_id)),None)
    if not account: raise RuntimeError("Postfach nicht gefunden.")
    return account


@router.get("/mail/accounts/{account_id}/messages", dependencies=auth)
async def mail_messages(account_id: str, folder: str = "INBOX", limit: int = 50) -> dict[str, Any]:
    def load():
        c=_imap_connect(_mail_account(account_id))
        try:
            status,_=c.select(folder,readonly=True)
            if status!="OK": raise RuntimeError("Ordner konnte nicht geöffnet werden.")
            _,data=c.search(None,"ALL"); ids=(data[0].split() if data and data[0] else [])[-max(1,min(limit,200)):]
            out=[]
            for uid in reversed(ids):
                _,parts=c.fetch(uid,"(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)] FLAGS)")
                raw=next((p[1] for p in parts if isinstance(p,tuple)),b""); msg=email.message_from_bytes(raw,policy=email_policy.default)
                out.append({"uid":uid.decode(),"from":_decode_mail_header(str(msg.get("From") or "")),"to":_decode_mail_header(str(msg.get("To") or "")),"subject":_decode_mail_header(str(msg.get("Subject") or "(ohne Betreff)")),"date":str(msg.get("Date") or "")})
            return out
        finally:
            try:c.logout()
            except Exception:pass
    try:return {"ok":True,"items":await asyncio.to_thread(load)}
    except Exception as exc:raise HTTPException(status_code=502,detail=f"Postfach konnte nicht geladen werden: {exc}") from exc


@router.get("/mail/accounts/{account_id}/messages/{uid}", dependencies=auth)
async def mail_message_get(account_id: str, uid: str, folder: str = "INBOX") -> dict[str, Any]:
    def load():
        c=_imap_connect(_mail_account(account_id))
        try:
            c.select(folder,readonly=True); _,parts=c.fetch(str(uid),"(RFC822)"); raw=next((p[1] for p in parts if isinstance(p,tuple)),b""); msg=email.message_from_bytes(raw,policy=email_policy.default)
            body=""
            parts_iter=msg.walk() if msg.is_multipart() else [msg]
            for part in parts_iter:
                if part.get_content_disposition()=="attachment":continue
                if part.get_content_type()=="text/plain": body=part.get_content(); break
                if not body and part.get_content_type()=="text/html": body=re.sub(r"<[^>]+>"," ",part.get_content())
            return {"uid":uid,"from":_decode_mail_header(str(msg.get("From") or "")),"to":_decode_mail_header(str(msg.get("To") or "")),"subject":_decode_mail_header(str(msg.get("Subject") or "")),"date":str(msg.get("Date") or ""),"body":str(body or "")}
        finally:
            try:c.logout()
            except Exception:pass
    try:return {"ok":True,"item":await asyncio.to_thread(load)}
    except Exception as exc:raise HTTPException(status_code=502,detail=f"E-Mail konnte nicht geöffnet werden: {exc}") from exc


@router.post("/mail/accounts/{account_id}/send", dependencies=auth)
async def mail_account_send(account_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}; account=_mail_account(account_id)
    to=str(body.get("to") or "").strip(); cc=str(body.get("cc") or "").strip(); bcc=str(body.get("bcc") or "").strip()
    if not to or "@" not in to: raise HTTPException(status_code=400,detail="Empfängeradresse fehlt.")
    raw_attachments=body.get("attachments") if isinstance(body.get("attachments"),list) else []
    attachments=[]; total_size=0
    for item in raw_attachments:
        if not isinstance(item,dict): continue
        encoded=str(item.get("data") or "")
        if "," in encoded and encoded.lower().startswith("data:"): encoded=encoded.split(",",1)[1]
        try: raw=base64.b64decode(encoded,validate=True)
        except Exception: raise HTTPException(status_code=400,detail=f"Anhang {str(item.get('name') or '')} ist ungültig.")
        total_size += len(raw)
        if total_size > 20*1024*1024: raise HTTPException(status_code=413,detail="Anhänge sind zusammen größer als 20 MB.")
        attachments.append((str(item.get("name") or "Anhang"),str(item.get("mime") or "application/octet-stream"),raw))
    def send():
        sender_address = str(account.get("email") or account.get("username") or "")
        msg=EmailMessage(); msg["Subject"]=str(body.get("subject") or ""); msg["From"]=f'{account.get("from_name") or "HCA"} <{sender_address}>'; msg["To"]=to
        if cc: msg["Cc"]=cc
        if bcc: msg["Bcc"]=bcc
        if account.get("reply_to"):msg["Reply-To"]=str(account["reply_to"])
        msg.set_content(str(body.get("message") or ""))
        html_body = str(body.get("html") or "").strip()
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        for filename,mime,raw in attachments:
            parts=str(mime or "application/octet-stream").split("/",1); main=parts[0] or "application"; sub=parts[1] if len(parts)>1 else "octet-stream"
            msg.add_attachment(raw,maintype=main,subtype=sub,filename=filename)
        host=str(account.get("smtp_host") or ""); port=int(account.get("smtp_port") or 587); security=str(account.get("smtp_security") or "starttls")
        if not host: raise RuntimeError("SMTP-Server fehlt.")
        smtp=smtplib.SMTP_SSL(host,port,timeout=30) if security=="ssl" else smtplib.SMTP(host,port,timeout=30)
        try:
            if security=="starttls":smtp.starttls()
            smtp.login(str(account.get("username") or account.get("email") or ""),str(account.get("smtp_password") or account.get("imap_password") or "")); smtp.send_message(msg)
        finally:smtp.quit()
    try:await asyncio.to_thread(send);return {"ok":True,"attachments":len(attachments)}
    except Exception as exc:raise HTTPException(status_code=502,detail=f"E-Mail konnte nicht gesendet werden: {exc}") from exc


# ---------------------------------------------------------------------------
# HCA v0.13.0 · suppliers, own products and isolated Woo customer portal
# ---------------------------------------------------------------------------

def _email_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _supplier_values(payload: dict[str, Any]) -> dict[str, Any]:
    fields = ("name", "code", "contact_name", "email", "phone", "website", "street", "zip", "city", "country", "customer_no", "notes", "api_type", "api_base_url")
    values = {key: str(payload.get(key) or "").strip() for key in fields}
    if not values["name"]:
        raise HTTPException(status_code=400, detail="Bitte einen Lieferantennamen angeben.")
    values["country"] = values["country"] or "DE"
    values["active"] = 1 if payload.get("active", True) else 0
    return values


@router.get("/crm/suppliers", dependencies=auth)
async def crm_suppliers(q: str = "", active: int = 1, limit: int = 1000) -> dict[str, Any]:
    with _db() as conn:
        where = ["active=?"] if int(active) >= 0 else []
        args: list[Any] = [1 if int(active) else 0] if where else []
        if str(q or "").strip():
            like = f"%{str(q).strip()}%"
            where.append("(name LIKE ? OR code LIKE ? OR contact_name LIKE ? OR email LIKE ? OR city LIKE ? OR customer_no LIKE ?)")
            args.extend([like] * 6)
        sql = "SELECT * FROM suppliers" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY name COLLATE NOCASE LIMIT ?"
        args.append(max(1, min(int(limit or 1000), 2000)))
        return {"ok": True, "items": [dict(x) for x in conn.execute(sql, args).fetchall()]}


@router.post("/crm/suppliers", dependencies=auth)
async def crm_supplier_create(request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}
    values = _supplier_values(payload); sid = str(uuid.uuid4()); now = _now()
    with _db() as conn:
        conn.execute("""INSERT INTO suppliers(id,name,code,contact_name,email,phone,website,street,zip,city,country,customer_no,notes,api_type,api_base_url,active,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (sid, values["name"], values["code"], values["contact_name"], values["email"], values["phone"], values["website"], values["street"], values["zip"], values["city"], values["country"], values["customer_no"], values["notes"], values["api_type"], values["api_base_url"], values["active"], now, now))
        return {"ok": True, "item": dict(conn.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone())}


@router.put("/crm/suppliers/{supplier_id}", dependencies=auth)
async def crm_supplier_update(supplier_id: str, request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}; values = _supplier_values(payload)
    with _db() as conn:
        if not conn.execute("SELECT 1 FROM suppliers WHERE id=?", (supplier_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Lieferant nicht gefunden.")
        conn.execute("""UPDATE suppliers SET name=?,code=?,contact_name=?,email=?,phone=?,website=?,street=?,zip=?,city=?,country=?,customer_no=?,notes=?,api_type=?,api_base_url=?,active=?,updated_at=? WHERE id=?""",
                     (values["name"], values["code"], values["contact_name"], values["email"], values["phone"], values["website"], values["street"], values["zip"], values["city"], values["country"], values["customer_no"], values["notes"], values["api_type"], values["api_base_url"], values["active"], _now(), supplier_id))
        return {"ok": True, "item": dict(conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone())}


@router.post("/inventory/articles", dependencies=auth)
async def inventory_article_create(request: Request) -> dict[str, Any]:
    payload = await request.json(); payload = payload if isinstance(payload, dict) else {}
    name = str(payload.get("name") or "").strip(); sku = str(payload.get("sku") or "").strip()
    if not name or not sku:
        raise HTTPException(status_code=400, detail="Artikelname und SKU sind Pflichtfelder.")
    description = str(payload.get("description") or "").strip()
    manufacturer = str(payload.get("manufacturer") or "").strip()
    supplier = str(payload.get("supplier") or "").strip()
    unit_price = max(0.0, float(payload.get("unit_price") or 0)); tax_rate = max(0.0, float(payload.get("tax_rate") if payload.get("tax_rate") is not None else 19))
    list_in_shop = bool(payload.get("list_in_shop")); shop_status = ""
    woo_product_id = ""; woo_data: dict[str, Any] = {}
    with _db() as conn:
        if conn.execute("SELECT 1 FROM inventory_articles WHERE lower(sku)=lower(?)", (sku,)).fetchone():
            raise HTTPException(status_code=409, detail="Diese SKU ist bereits im Artikelstamm vorhanden.")
        supplier_id = str(payload.get("supplier_id") or "")
        if supplier_id:
            row = conn.execute("SELECT name FROM suppliers WHERE id=? AND active=1", (supplier_id,)).fetchone()
            if row: supplier = str(row["name"] or supplier)
    if list_in_shop:
        requested_status = str(payload.get("shop_status") or "draft").lower()
        shop_status = requested_status if requested_status in {"draft", "publish"} else "draft"
        woo_payload = {"name": name, "type": "simple", "status": shop_status, "sku": sku, "regular_price": f"{unit_price:.2f}", "description": description, "tax_status": "taxable", "manage_stock": False}
        try:
            result = await asyncio.to_thread(_woo_request, "/products", "POST", woo_payload)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Artikel wurde nicht angelegt, weil WooCommerce nicht geschrieben werden konnte: {exc}") from exc
        if isinstance(result, dict):
            woo_data = result; woo_product_id = str(result.get("id") or "")
    raw = woo_data or {"name": name, "sku": sku, "description": description, "regular_price": f"{unit_price:.2f}", "status": shop_status or "hca-only", "source": "hca"}
    with _db() as conn:
        article_id = _ensure_inventory_article(conn, woo_product_id=woo_product_id, name=name, sku=sku, manufacturer=manufacturer, supplier=supplier, raw=raw)
        conn.execute("UPDATE inventory_articles SET description=?,unit_price=?,tax_rate=?,source='hca',shop_status=?,updated_at=? WHERE id=?", (description, unit_price, tax_rate, shop_status, _now(), article_id))
        _ensure_stock_item(conn, article_id=article_id, woo_product_id=woo_product_id, sku=sku, erp_code="", color="", size="")
        return {"ok": True, "article": _inventory_article_detail(conn, article_id), "woo_created": bool(woo_product_id)}


def _merge_customer_duplicates(conn: sqlite3.Connection, email_key: str) -> tuple[sqlite3.Row | None, int]:
    rows = conn.execute("SELECT * FROM crm_customers WHERE active=1 AND lower(trim(email))=? ORDER BY CASE WHEN woo_customer_id<>'' THEN 0 ELSE 1 END,created_at,id", (email_key,)).fetchall()
    if not rows: return None, 0
    keep = rows[0]; merged = 0
    for duplicate in rows[1:]:
        source_id = str(duplicate["id"]); target_id = str(keep["id"])
        merge_fields = ("company_name","salutation","first_name","last_name","phone","mobile","website","vat_id","tax_no","billing_street","billing_zip","billing_city","billing_country","shipping_street","shipping_zip","shipping_city","shipping_country","payment_term_id","woo_customer_id")
        merged_values = {field: (str(keep[field] or "") or str(duplicate[field] or "")) for field in merge_fields}
        conn.execute("""UPDATE crm_customers SET company_name=?,salutation=?,first_name=?,last_name=?,phone=?,mobile=?,website=?,vat_id=?,tax_no=?,billing_street=?,billing_zip=?,billing_city=?,billing_country=?,shipping_street=?,shipping_zip=?,shipping_city=?,shipping_country=?,payment_term_id=?,woo_customer_id=?,updated_at=? WHERE id=?""", (*[merged_values[field] for field in merge_fields], _now(), target_id))
        for table in ("crm_contacts", "crm_addresses", "sales_quotes", "sales_orders", "finance_invoices", "delivery_notes"):
            conn.execute(f"UPDATE {table} SET customer_id=? WHERE customer_id=?", (target_id, source_id))
        note = f"\nZusammengeführt mit {keep['customer_no']} am {_now()[:10]}.".strip()
        conn.execute("UPDATE crm_customers SET active=0,notes=trim(notes || ?),updated_at=? WHERE id=?", ("\n" + note, _now(), source_id))
        merged += 1
        keep = conn.execute("SELECT * FROM crm_customers WHERE id=?", (target_id,)).fetchone()
    return conn.execute("SELECT * FROM crm_customers WHERE id=?", (keep["id"],)).fetchone(), merged


def _woo_customer_pages() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(1, 101):
        data = _woo_request(f"/customers?per_page=100&page={page}&orderby=id&order=asc")
        if not isinstance(data, list) or not data: break
        items.extend(x for x in data if isinstance(x, dict))
        if len(data) < 100: break
    return items


def _portal_customer_directory(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM crm_customers WHERE active=1 AND trim(email)<>'' ORDER BY customer_no").fetchall()
    return [{"hca_customer_id": str(x["id"]), "customer_no": str(x["customer_no"]), "woo_customer_id": str(x["woo_customer_id"] or ""), "email": _email_key(x["email"]), "company_name": str(x["company_name"] or ""), "first_name": str(x["first_name"] or ""), "last_name": str(x["last_name"] or ""), "street": str(x["billing_street"] or ""), "zip": str(x["billing_zip"] or ""), "city": str(x["billing_city"] or ""), "country": str(x["billing_country"] or "DE"), "complete": bool(str(x["email"] or "").strip() and str(x["billing_street"] or "").strip() and str(x["billing_zip"] or "").strip() and str(x["billing_city"] or "").strip())} for x in rows]


def _woocommerce_customer_sync_blocking() -> dict[str, Any]:
    remote = _woo_customer_pages(); created = updated = merged = 0; warnings: list[str] = []
    with _db() as conn:
        for wc in remote:
            email_key = _email_key(wc.get("email"))
            if not email_key: continue
            customer, duplicate_count = _merge_customer_duplicates(conn, email_key); merged += duplicate_count
            billing = wc.get("billing") if isinstance(wc.get("billing"), dict) else {}
            shipping = wc.get("shipping") if isinstance(wc.get("shipping"), dict) else {}
            company = str(billing.get("company") or shipping.get("company") or wc.get("company") or "").strip()
            first_name = str(wc.get("first_name") or billing.get("first_name") or shipping.get("first_name") or "").strip()
            last_name = str(wc.get("last_name") or billing.get("last_name") or shipping.get("last_name") or "").strip()
            username = str(wc.get("username") or "").strip()
            if not (first_name or last_name) and username and "@" not in username:
                parts = username.replace(".", " ").replace("_", " ").replace("-", " ").split()
                if len(parts) > 1:
                    first_name, last_name = " ".join(parts[:-1]).title(), parts[-1].title()
                elif parts:
                    last_name = parts[0].title()
            incoming = {"company_name": company, "first_name": first_name, "last_name": last_name, "email": email_key, "phone": billing.get("phone") or shipping.get("phone"), "billing_street": " ".join(x for x in [str(billing.get("address_1") or "").strip(), str(billing.get("address_2") or "").strip()] if x), "billing_zip": billing.get("postcode"), "billing_city": billing.get("city"), "billing_country": billing.get("country") or "DE", "shipping_street": " ".join(x for x in [str(shipping.get("address_1") or "").strip(), str(shipping.get("address_2") or "").strip()] if x), "shipping_zip": shipping.get("postcode"), "shipping_city": shipping.get("city"), "shipping_country": shipping.get("country") or billing.get("country") or "DE"}
            if not customer:
                cid = str(uuid.uuid4()); now = _now(); no = _business_next_no(conn, "customer", "KD")
                conn.execute("""INSERT INTO crm_customers(id,customer_no,customer_type,company_name,first_name,last_name,email,phone,billing_street,billing_zip,billing_city,billing_country,shipping_street,shipping_zip,shipping_city,shipping_country,woo_customer_id,woo_synced_at,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (cid,no,"customer",str(incoming["company_name"] or ""),str(incoming["first_name"] or ""),str(incoming["last_name"] or ""),email_key,str(incoming["phone"] or ""),str(incoming["billing_street"] or ""),str(incoming["billing_zip"] or ""),str(incoming["billing_city"] or ""),str(incoming["billing_country"] or "DE"),str(incoming["shipping_street"] or ""),str(incoming["shipping_zip"] or ""),str(incoming["shipping_city"] or ""),str(incoming["shipping_country"] or "DE"),str(wc.get("id") or ""),now,1,now,now))
                _business_sync_customer_default_addresses(conn, cid, incoming); created += 1
            else:
                updates = {key: (str(customer[key] or "") or str(value or "")) for key, value in incoming.items() if key in customer.keys()}
                conn.execute("""UPDATE crm_customers SET company_name=?,first_name=?,last_name=?,email=?,phone=?,billing_street=?,billing_zip=?,billing_city=?,billing_country=?,shipping_street=?,shipping_zip=?,shipping_city=?,shipping_country=?,woo_customer_id=?,woo_synced_at=?,updated_at=? WHERE id=?""", (updates.get("company_name",""),updates.get("first_name",""),updates.get("last_name",""),email_key,updates.get("phone",""),updates.get("billing_street",""),updates.get("billing_zip",""),updates.get("billing_city",""),updates.get("billing_country","DE"),updates.get("shipping_street",""),updates.get("shipping_zip",""),updates.get("shipping_city",""),updates.get("shipping_country","DE"),str(wc.get("id") or ""),_now(),_now(),customer["id"]))
                _business_sync_customer_default_addresses(conn, str(customer["id"]), updates); updated += 1
        directory = _portal_customer_directory(conn)
    try:
        _woo_request("/customer-directory", "POST", {"customers": directory}, api_namespace="wsk-hca/v1")
    except Exception as exc:
        warnings.append(f"Kundenportal-Verzeichnis: {exc}")
    return {"remote": len(remote), "created": created, "updated": updated, "merged": merged, "directory": len(directory), "warnings": warnings}


@router.post("/woocommerce/customers/sync", dependencies=auth)
async def woocommerce_customers_sync() -> dict[str, Any]:
    try: return {"ok": True, **(await asyncio.to_thread(_woocommerce_customer_sync_blocking))}
    except Exception as exc: raise HTTPException(status_code=502, detail=f"Kundenabgleich fehlgeschlagen: {exc}") from exc


def _portal_documents() -> list[dict[str, Any]]:
    # Gather all records first. PDF rendering reads shared settings through a
    # separate connection, so the source connection must be closed beforehand.
    jobs: list[dict[str, Any]] = []
    with _db() as conn:
        def link_for(customer_id: str) -> dict[str, str] | None:
            customer = conn.execute("SELECT email,woo_customer_id FROM crm_customers WHERE id=? AND active=1", (customer_id,)).fetchone()
            if not customer or not _email_key(customer["email"]): return None
            return {"email": _email_key(customer["email"]), "woo_customer_id": str(customer["woo_customer_id"] or "")}
        for row in conn.execute("SELECT * FROM sales_quotes WHERE status<>'draft' AND customer_id<>''").fetchall():
            link = link_for(str(row["customer_id"])); customer = conn.execute("SELECT * FROM crm_customers WHERE id=?", (row["customer_id"],)).fetchone()
            if link: jobs.append({"kind":"quote","row":dict(row),"document":_business_quote_dict(conn,row,True),"address":_business_customer_snapshot(conn,customer,str(row["contact_id"] or ""),str(row["billing_address_id"] or ""),str(row["shipping_address_id"] or ""))[0] if customer else {},"link":link})
        for row in conn.execute("SELECT * FROM sales_orders WHERE status NOT IN ('draft','cancelled') AND customer_id<>''").fetchall():
            link = link_for(str(row["customer_id"])); document = _business_order_dict(conn,row,True)
            if link: jobs.append({"kind":"order","row":dict(row),"document":document,"address":document.get("billing") or {},"link":link})
        for row in conn.execute("SELECT * FROM finance_invoices WHERE direction='customer' AND status NOT IN ('draft','voided','cancelled') AND customer_id<>''").fetchall():
            link = link_for(str(row["customer_id"])); document = _finance_invoice_dict(conn,row,True)
            if link: jobs.append({"kind":"invoice","row":dict(row),"document":document,"address":document.get("billing") or {},"link":link})
        for row in conn.execute("SELECT * FROM delivery_notes WHERE status<>'draft' AND customer_id<>''").fetchall():
            link = link_for(str(row["customer_id"])); document = _delivery_note_dict(conn,row,True)
            if link: jobs.append({"kind":"delivery_note","row":dict(row),"document":document,"address":{},"link":link})
    docs: list[dict[str, Any]] = []
    for job in jobs:
        kind = str(job["kind"]); row = job["row"]; document = job["document"]; link = job["link"]
        number = str(row.get("quote_no") or row.get("order_no") or row.get("invoice_no") or row.get("delivery_note_no") or "")
        date_value = str(row.get("invoice_date") or row.get("delivery_date") or row.get("created_at") or "")
        title = str(row.get("subject") or ("Lieferschein" if kind == "delivery_note" else number))
        raw_pdf = _delivery_pdf_bytes(document) if kind == "delivery_note" else _commercial_pdf_bytes(kind, document, job["address"])
        docs.append({"hca_document_id": str(row["id"]), "document_type": kind, "document_number": number, "status": str(row.get("status") or ""), "document_date": date_value, "title": title, "customer_email": link["email"], "woo_customer_id": link["woo_customer_id"], "filename": re.sub(r"[^A-Za-z0-9._-]+", "_", f"{kind}_{number}.pdf"), "pdf_base64": base64.b64encode(raw_pdf).decode("ascii")})
    return docs


def _portal_sync_blocking() -> dict[str, Any]:
    with _db() as conn:
        directory = _portal_customer_directory(conn)
    documents = _portal_documents()
    _woo_request("/customer-directory", "POST", {"customers": directory}, api_namespace="wsk-hca/v1")
    sent = 0
    for start in range(0, len(documents), 10):
        batch = documents[start:start + 10]
        _woo_request("/customer-documents", "POST", {"documents": batch}, api_namespace="wsk-hca/v1", timeout=120); sent += len(batch)
    return {"customers": len(directory), "documents": sent}


@router.post("/woocommerce/customer-portal/sync", dependencies=auth)
async def woocommerce_customer_portal_sync() -> dict[str, Any]:
    try: return {"ok": True, **(await asyncio.to_thread(_portal_sync_blocking))}
    except Exception as exc: raise HTTPException(status_code=502, detail=f"Kundenportal-Abgleich fehlgeschlagen: {exc}") from exc


# ---------------------------------------------------------------------------
# HCA v0.13.4 · echte Lexware-Rechnungen und Rechnungskorrekturen
# ---------------------------------------------------------------------------
def _hca134_date(value: Any) -> str:
    text=str(value or _finance_today()).strip()[:10]
    return f"{text}T00:00:00.000Z"

def _hca134_address(row: sqlite3.Row) -> dict[str, Any]:
    data=_loads(row["billing_json"],{}) if row["billing_json"] else {}
    name=str(data.get("name") or data.get("company_name") or row["customer_name"] or "Kunde").strip()
    country=str(data.get("countryCode") or data.get("country") or "DE").strip().upper()
    if len(country)!=2: country="DE"
    result={"name":name,"countryCode":country}
    mapping={"supplement":"attention","street":"street","zip":"zip","city":"city"}
    for target,source in mapping.items():
        value=str(data.get(source) or "").strip()
        if value: result[target]=value
    return result

def _hca134_line_items(conn: sqlite3.Connection, invoice_id: str, credit: bool=False) -> list[dict[str, Any]]:
    rows=conn.execute("SELECT * FROM finance_invoice_items WHERE invoice_id=? ORDER BY position_no,id",(invoice_id,)).fetchall()
    items=[]
    for row in rows:
        description=str(row["description"] or "Position").strip()
        item={"type":"custom","name":description[:255],"quantity":abs(float(row["quantity"] or 1)),"unitName":str(row["unit"] or "Stk.")[:25],"unitPrice":{"currency":"EUR","netAmount":round(abs(float(row["unit_price"] or 0)),4),"taxRatePercentage":float(row["tax_rate"] or 0)}}
        if not credit: item["discountPercentage"]=max(0.0,min(100.0,float(row["discount_pct"] or 0)))
        items.append(item)
    if not items: raise RuntimeError("Die Rechnung enthält keine Positionen.")
    return items

def _hca134_invoice_payload(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    days=14
    try:
        start=datetime.fromisoformat(str(row["invoice_date"])[:10]).date()
        due=datetime.fromisoformat(str(row["due_date"])[:10]).date()
        days=max(0,(due-start).days)
    except Exception: pass
    return {"archived":False,"voucherDate":_hca134_date(row["invoice_date"]),"address":_hca134_address(row),"lineItems":_hca134_line_items(conn,str(row["id"]),False),"totalPrice":{"currency":"EUR"},"taxConditions":{"taxType":"net"},"paymentConditions":{"paymentTermLabel":str(row["payment_term_text"] or f"Zahlbar innerhalb von {days} Tagen."),"paymentTermDuration":days},"shippingConditions":{"shippingType":"none"},"title":"Rechnung","introduction":f"Rechnung {row['invoice_no']}","remark":str(row["notes"] or "Vielen Dank für Ihren Auftrag.")}

def _hca134_credit_payload(conn: sqlite3.Connection, row: sqlite3.Row, reason: str) -> dict[str, Any]:
    return {"archived":False,"voucherDate":_hca134_date(_finance_today()),"address":_hca134_address(row),"lineItems":_hca134_line_items(conn,str(row["id"]),True),"totalPrice":{"currency":"EUR"},"taxConditions":{"taxType":"net"},"title":"Rechnungskorrektur","introduction":f"Rechnungskorrektur zur Rechnung {row['invoice_no']}","remark":reason}

def _hca134_send_invoice(invoice_id: str) -> dict[str, Any]:
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row: raise RuntimeError("Rechnung nicht gefunden.")
        if row["status"]=="draft": raise RuntimeError("Bitte die Kundenrechnung zuerst festschreiben.")
        if row["direction"]!="customer": raise RuntimeError("Nur Kundenrechnungen werden als Lexware-Verkaufsbeleg übertragen.")
        if row["lexware_voucher_id"]:
            return _finance_invoice_dict(conn,row,True)
        payload=_hca134_invoice_payload(conn,row)
    created=_lexware_request("/v1/invoices?finalize=true","POST",payload,"application/json",45)
    vid=str(created.get("id") or "") if isinstance(created,dict) else ""
    if not vid: raise RuntimeError("Lexware hat keine Rechnungs-ID zurückgegeben.")
    now=_now()
    with _db() as conn:
        conn.execute("UPDATE finance_invoices SET lexware_voucher_id=?,lexware_voucher_type='invoice',lexware_status='open',lexware_open_amount=?,lexware_deeplink=?,lexware_synced_at=?,updated_at=? WHERE id=?",(vid,float(conn.execute("SELECT total_gross FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()[0] or 0),_finance_deeplink("invoice",vid),now,now,invoice_id))
        return _finance_invoice_dict(conn,conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone(),True)

@router.post("/finance/invoices/{invoice_id}/lexware", dependencies=auth)
async def hca134_invoice_to_lexware(invoice_id: str) -> dict[str, Any]:
    try:
        item=await asyncio.to_thread(_hca134_send_invoice,invoice_id)
        return {"ok":True,"item":item}
    except Exception as exc:
        raise HTTPException(status_code=502,detail=str(exc)) from exc

@router.post("/finance/invoices/{invoice_id}/credit-note", dependencies=auth)
async def hca134_create_credit_note(invoice_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    reason=str(body.get("reason") or "").strip()
    requested=str(body.get("settlement_method") or "").strip()
    if not reason: raise HTTPException(status_code=400,detail="Bitte einen Grund für die Stornierung angeben.")
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Rechnung nicht gefunden.")
        if row["direction"]!="customer" or row["status"]=="draft": raise HTTPException(status_code=409,detail="Nur festgeschriebene Kundenrechnungen können storniert werden.")
        existing=conn.execute("SELECT * FROM finance_credit_notes WHERE invoice_id=?",(invoice_id,)).fetchone()
        if existing: return {"ok":True,"invoice":_finance_invoice_dict(conn,row,True),"credit_note":dict(existing),"already_exists":True}
    try:
        invoice=await asyncio.to_thread(_hca134_send_invoice,invoice_id)
    except Exception as exc:
        raise HTTPException(status_code=502,detail=f"Die Rechnung konnte nicht korrekt an Lexware übertragen werden: {exc}") from exc
    lexware_id=str(invoice.get("lexware_voucher_id") or "")
    paid=str(invoice.get("payment_status") or "").lower() in {"paid","paidoff"} or (invoice.get("lexware_open_amount") is not None and float(invoice.get("lexware_open_amount") or 0)==0)
    if lexware_id:
        try:
            payment=await asyncio.to_thread(_lexware_request,f"/v1/payments/{urllib.parse.quote(lexware_id,safe='')}","GET",None,"application/json",30)
            paid=str(payment.get("paymentStatus") or "")=="balanced" or str(payment.get("voucherStatus") or "") in {"paid","paidoff"}
        except Exception:
            pass
    settlement=requested if paid and requested in {"refund","customer_credit"} else "offset"
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        payload=_hca134_credit_payload(conn,row,reason)
    linked_invoice=str(invoice.get("lexware_voucher_type") or "")=="invoice"
    path=(f"/v1/credit-notes?precedingSalesVoucherId={urllib.parse.quote(lexware_id,safe='')}&finalize=true" if linked_invoice else "/v1/credit-notes?finalize=true")
    try:
        created=await asyncio.to_thread(_lexware_request,path,"POST",payload,"application/json",45)
    except Exception as exc:
        raise HTTPException(status_code=502,detail=f"Lexware hat die Rechnungskorrektur abgelehnt: {exc}") from exc
    credit_lexware_id=str(created.get("id") or "") if isinstance(created,dict) else ""
    if not credit_lexware_id: raise HTTPException(status_code=502,detail="Lexware hat keine Gutschrift-ID zurückgegeben.")
    now=_now()
    with _db() as conn:
        row=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        cid=str(uuid.uuid4()); number=_business_next_no(conn,"credit_note","GS")
        settlement_status="pending" if settlement=="refund" else "booked"
        deeplink=_finance_deeplink("creditnote",credit_lexware_id)
        conn.execute("INSERT INTO finance_credit_notes(id,credit_note_no,invoice_id,customer_id,customer_name,reason,settlement_method,settlement_status,total_net,total_tax,total_gross,lexware_voucher_id,lexware_status,lexware_deeplink,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cid,number,invoice_id,str(row["customer_id"] or ""),str(row["customer_name"] or ""),reason,settlement,settlement_status,float(row["total_net"] or 0),float(row["total_tax"] or 0),float(row["total_gross"] or 0),credit_lexware_id,"paidoff" if linked_invoice else "open",deeplink,now,now))
        if settlement=="customer_credit" and row["customer_id"]:
            conn.execute("UPDATE crm_customers SET credit_balance=COALESCE(credit_balance,0)+?,updated_at=? WHERE id=?",(float(row["total_gross"] or 0),now,row["customer_id"]))
        conn.execute("UPDATE finance_invoices SET status='voided',credit_note_id=?,credit_note_no=?,updated_at=? WHERE id=?",(cid,number,now,invoice_id))
        updated=conn.execute("SELECT * FROM finance_invoices WHERE id=?",(invoice_id,)).fetchone()
        credit=conn.execute("SELECT * FROM finance_credit_notes WHERE id=?",(cid,)).fetchone()
        return {"ok":True,"invoice":_finance_invoice_dict(conn,updated,True),"credit_note":dict(credit)}


# ---------------------------------------------------------------------------
# HCA v0.13.5 · persönliche Benutzerkonten und Sitzungen
# ---------------------------------------------------------------------------
import hashlib as _hca135_hashlib
import hmac as _hca135_hmac
import secrets as _hca135_secrets

_HCA135_PASSWORD_ITERATIONS = 600000
_HCA135_SESSION_HOURS = 12
_HCA135_REMEMBER_DAYS = 30

def _hca135_user_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS hca_desktop_users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'employee',
            password_hash TEXT NOT NULL,
            signature_html TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS hca_desktop_user_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES hca_desktop_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_hca_desktop_user_sessions_user ON hca_desktop_user_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_hca_desktop_user_sessions_expires ON hca_desktop_user_sessions(expires_at);
    """)

def _hca135_now_dt() -> datetime:
    return datetime.now(timezone.utc)

def _hca135_iso(value: datetime | None = None) -> str:
    return (value or _hca135_now_dt()).isoformat()

def _hca135_password_hash(password: str) -> str:
    raw=str(password or "")
    if len(raw)<8: raise ValueError("Das Passwort muss mindestens 8 Zeichen lang sein.")
    salt=_hca135_secrets.token_bytes(16)
    digest=_hca135_hashlib.pbkdf2_hmac("sha256",raw.encode("utf-8"),salt,_HCA135_PASSWORD_ITERATIONS)
    return "pbkdf2_sha256$"+str(_HCA135_PASSWORD_ITERATIONS)+"$"+salt.hex()+"$"+digest.hex()

def _hca135_password_valid(password: str, encoded: str) -> bool:
    try:
        scheme,iterations,salt_hex,digest_hex=str(encoded or "").split("$",3)
        if scheme!="pbkdf2_sha256": return False
        digest=_hca135_hashlib.pbkdf2_hmac("sha256",str(password or "").encode("utf-8"),bytes.fromhex(salt_hex),int(iterations))
        return _hca135_hmac.compare_digest(digest.hex(),digest_hex)
    except Exception:
        return False

def _hca135_token_hash(token: str) -> str:
    return _hca135_hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()

def _hca135_public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item=dict(row)
    return {key:item.get(key) for key in ("id","username","display_name","role","signature_html","active","created_at","updated_at","last_login_at")}

def _hca135_session_user(token: str) -> dict[str, Any] | None:
    if not str(token or ""): return None
    with _db() as conn:
        _hca135_user_schema(conn)
        now=_hca135_iso()
        conn.execute("DELETE FROM hca_desktop_user_sessions WHERE expires_at<=?",(now,))
        row=conn.execute("""SELECT u.* FROM hca_desktop_user_sessions s
            JOIN hca_desktop_users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",(_hca135_token_hash(token),now)).fetchone()
        return _hca135_public_user(row) if row else None

def _hca135_requires_user_session(path: str) -> bool:
    tail=str(path or "").split("/api/hca-shared",1)[-1]
    public_prefixes=("/auth/","/mobile","/pair","/portal","/public","/health","/status","/version")
    if any(tail.startswith(prefix) for prefix in public_prefixes): return False
    try:
        with _db() as conn:
            _hca135_user_schema(conn)
            return bool(conn.execute("SELECT 1 FROM hca_desktop_users WHERE active=1 LIMIT 1").fetchone())
    except Exception:
        return False

def _hca135_current_user(token: str, admin: bool=False) -> dict[str, Any]:
    user=_hca135_session_user(token)
    if not user: raise HTTPException(status_code=401,detail="HCA-Anmeldung erforderlich.")
    if admin and user.get("role")!="admin": raise HTTPException(status_code=403,detail="Administratorrechte erforderlich.")
    return user

def _hca135_username(value: Any) -> str:
    username=str(value or "").strip().lower()
    if len(username)<3 or len(username)>64 or not all(ch.isalnum() or ch in "._-" for ch in username):
        raise HTTPException(status_code=400,detail="Der Benutzername benötigt 3 bis 64 Zeichen und darf Buchstaben, Zahlen, Punkt, Minus und Unterstrich enthalten.")
    return username

def _hca135_create_session(conn: sqlite3.Connection, user_id: str, remember: bool=False) -> tuple[str,str]:
    token=_hca135_secrets.token_urlsafe(48)
    expires=_hca135_now_dt()+(timedelta(days=_HCA135_REMEMBER_DAYS) if remember else timedelta(hours=_HCA135_SESSION_HOURS))
    conn.execute("INSERT INTO hca_desktop_user_sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",(_hca135_token_hash(token),user_id,_hca135_iso(),_hca135_iso(expires)))
    return token,_hca135_iso(expires)

@router.get("/auth/status", dependencies=auth)
async def hca135_auth_status(x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    with _db() as conn:
        _hca135_user_schema(conn)
        configured=bool(conn.execute("SELECT 1 FROM hca_desktop_users WHERE active=1 LIMIT 1").fetchone())
    user=_hca135_session_user(str(x_hca_session or "")) if configured else None
    return {"ok":True,"users_configured":configured,"authenticated":bool(user),"user":user}

@router.post("/auth/bootstrap", dependencies=auth)
async def hca135_auth_bootstrap(request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    username=_hca135_username(body.get("username"))
    display=str(body.get("display_name") or "").strip()
    if not display: raise HTTPException(status_code=400,detail="Bitte den vollständigen Namen eingeben.")
    try: password_hash=_hca135_password_hash(str(body.get("password") or ""))
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    now=_hca135_iso(); uid=str(uuid.uuid4())
    with _db() as conn:
        _hca135_user_schema(conn)
        if conn.execute("SELECT 1 FROM hca_desktop_users LIMIT 1").fetchone():
            raise HTTPException(status_code=409,detail="Die Benutzerverwaltung wurde bereits eingerichtet.")
        conn.execute("INSERT INTO hca_desktop_users(id,username,display_name,role,password_hash,active,created_at,updated_at,last_login_at) VALUES(?,?,?,?,?,?,?,?,?)",(uid,username,display,"admin",password_hash,1,now,now,now))
        token,expires=_hca135_create_session(conn,uid,True)
        row=conn.execute("SELECT * FROM hca_desktop_users WHERE id=?",(uid,)).fetchone()
        return {"ok":True,"session_token":token,"expires_at":expires,"user":_hca135_public_user(row)}

@router.post("/auth/login", dependencies=auth)
async def hca135_auth_login(request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    username=str(body.get("username") or "").strip()
    password=str(body.get("password") or "")
    with _db() as conn:
        _hca135_user_schema(conn)
        row=conn.execute("SELECT * FROM hca_desktop_users WHERE username=? COLLATE NOCASE",(username,)).fetchone()
        if not row or not row["active"] or not _hca135_password_valid(password,str(row["password_hash"] or "")):
            raise HTTPException(status_code=401,detail="Benutzername oder Passwort ist falsch.")
        now=_hca135_iso()
        conn.execute("UPDATE hca_desktop_users SET last_login_at=?,updated_at=? WHERE id=?",(now,now,row["id"]))
        token,expires=_hca135_create_session(conn,str(row["id"]),bool(body.get("remember")))
        row=conn.execute("SELECT * FROM hca_desktop_users WHERE id=?",(row["id"],)).fetchone()
        return {"ok":True,"session_token":token,"expires_at":expires,"user":_hca135_public_user(row)}

@router.post("/auth/logout", dependencies=auth)
async def hca135_auth_logout(x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    if x_hca_session:
        with _db() as conn:
            _hca135_user_schema(conn)
            conn.execute("DELETE FROM hca_desktop_user_sessions WHERE token_hash=?",(_hca135_token_hash(x_hca_session),))
    return {"ok":True}

@router.get("/auth/profile", dependencies=auth)
async def hca135_auth_profile(x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    return {"ok":True,"user":_hca135_current_user(str(x_hca_session or ""))}

@router.put("/auth/profile", dependencies=auth)
async def hca135_auth_profile_put(request: Request, x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    current=_hca135_current_user(str(x_hca_session or ""))
    body=await request.json(); body=body if isinstance(body,dict) else {}
    display=str(body.get("display_name") or "").strip()
    if not display: raise HTTPException(status_code=400,detail="Der Anzeigename darf nicht leer sein.")
    signature=str(body.get("signature_html") or "")[:50000]
    password=str(body.get("new_password") or "")
    try: password_hash=_hca135_password_hash(password) if password else ""
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    now=_hca135_iso()
    with _db() as conn:
        _hca135_user_schema(conn)
        if password_hash:
            conn.execute("UPDATE hca_desktop_users SET display_name=?,signature_html=?,password_hash=?,updated_at=? WHERE id=?",(display,signature,password_hash,now,current["id"]))
            conn.execute("DELETE FROM hca_desktop_user_sessions WHERE user_id=? AND token_hash<>?",(current["id"],_hca135_token_hash(str(x_hca_session or ""))))
        else:
            conn.execute("UPDATE hca_desktop_users SET display_name=?,signature_html=?,updated_at=? WHERE id=?",(display,signature,now,current["id"]))
        row=conn.execute("SELECT * FROM hca_desktop_users WHERE id=?",(current["id"],)).fetchone()
        return {"ok":True,"user":_hca135_public_user(row)}

@router.get("/auth/users", dependencies=auth)
async def hca135_users_get(x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    _hca135_current_user(str(x_hca_session or ""),True)
    with _db() as conn:
        _hca135_user_schema(conn)
        rows=conn.execute("SELECT * FROM hca_desktop_users ORDER BY active DESC,display_name COLLATE NOCASE,username COLLATE NOCASE").fetchall()
        return {"ok":True,"items":[_hca135_public_user(row) for row in rows]}

@router.post("/auth/users", dependencies=auth)
async def hca135_users_post(request: Request, x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    _hca135_current_user(str(x_hca_session or ""),True)
    body=await request.json(); body=body if isinstance(body,dict) else {}
    username=_hca135_username(body.get("username"))
    display=str(body.get("display_name") or "").strip()
    if not display: raise HTTPException(status_code=400,detail="Bitte den vollständigen Namen eingeben.")
    role=str(body.get("role") or "employee")
    if role not in {"admin","employee"}: role="employee"
    try: password_hash=_hca135_password_hash(str(body.get("password") or ""))
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    now=_hca135_iso(); uid=str(uuid.uuid4())
    try:
        with _db() as conn:
            _hca135_user_schema(conn)
            conn.execute("INSERT INTO hca_desktop_users(id,username,display_name,role,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(uid,username,display,role,password_hash,1,now,now))
            return {"ok":True,"user":_hca135_public_user(conn.execute("SELECT * FROM hca_desktop_users WHERE id=?",(uid,)).fetchone())}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409,detail="Dieser Benutzername ist bereits vergeben.") from exc

@router.put("/auth/users/{user_id}", dependencies=auth)
async def hca135_users_put(user_id: str, request: Request, x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    current=_hca135_current_user(str(x_hca_session or ""),True)
    if str(current["id"])==str(user_id): raise HTTPException(status_code=409,detail="Das eigene Administratorkonto kann hier nicht deaktiviert oder herabgestuft werden.")
    body=await request.json(); body=body if isinstance(body,dict) else {}
    role=str(body.get("role") or "employee")
    if role not in {"admin","employee"}: role="employee"
    active=1 if bool(body.get("active",True)) else 0
    with _db() as conn:
        _hca135_user_schema(conn)
        row=conn.execute("SELECT * FROM hca_desktop_users WHERE id=?",(user_id,)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Benutzer nicht gefunden.")
        if row["role"]=="admin" and row["active"] and (role!="admin" or not active):
            other=conn.execute("SELECT 1 FROM hca_desktop_users WHERE role='admin' AND active=1 AND id<>? LIMIT 1",(user_id,)).fetchone()
            if not other: raise HTTPException(status_code=409,detail="Der letzte aktive Administrator kann nicht deaktiviert oder herabgestuft werden.")
        conn.execute("UPDATE hca_desktop_users SET role=?,active=?,updated_at=? WHERE id=?",(role,active,_hca135_iso(),user_id))
        if not active: conn.execute("DELETE FROM hca_desktop_user_sessions WHERE user_id=?",(user_id,))
        return {"ok":True,"user":_hca135_public_user(conn.execute("SELECT * FROM hca_desktop_users WHERE id=?",(user_id,)).fetchone())}

@router.put("/auth/users/{user_id}/password", dependencies=auth)
async def hca135_users_password(user_id: str, request: Request, x_hca_session: str | None = Header(default=None, alias="X-HCA-Session")) -> dict[str, Any]:
    _hca135_current_user(str(x_hca_session or ""),True)
    body=await request.json(); body=body if isinstance(body,dict) else {}
    try: password_hash=_hca135_password_hash(str(body.get("password") or ""))
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    with _db() as conn:
        _hca135_user_schema(conn)
        if not conn.execute("SELECT 1 FROM hca_desktop_users WHERE id=?",(user_id,)).fetchone(): raise HTTPException(status_code=404,detail="Benutzer nicht gefunden.")
        conn.execute("UPDATE hca_desktop_users SET password_hash=?,updated_at=? WHERE id=?",(password_hash,_hca135_iso(),user_id))
        conn.execute("DELETE FROM hca_desktop_user_sessions WHERE user_id=?",(user_id,))
    return {"ok":True}
