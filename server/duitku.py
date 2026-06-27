"""Duitku API wrapper — inquiry, callback verification, signature."""

import os
import hashlib
import httpx
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────

DUITKU_MERCHANT_CODE = os.environ.get("DUITKU_MERCHANT_CODE", "DSXXXX")
DUITKU_API_KEY = os.environ.get("DUITKU_API_KEY", "xxxxxxxx")
DUITKU_BASE_URL = os.environ.get(
    "DUITKU_BASE_URL", "https://api.duitku.com/api/merchant"
)
DUITKU_SANDBOX_URL = os.environ.get(
    "DUITKU_SANDBOX_URL", "https://sandbox.duitku.com/api/merchant"
)
DUITKU_SANDBOX = os.environ.get("DUITKU_SANDBOX", "true").lower() == "true"

CALLBACK_URL = os.environ.get("CALLBACK_URL", "https://domainkamu.com/api/payment/callback")
RETURN_URL = os.environ.get("RETURN_URL", "https://domainkamu.com/dashboard")

API_URL = DUITKU_SANDBOX_URL if DUITKU_SANDBOX else DUITKU_BASE_URL

# ── Package Pricing ─────────────────────────────────────────────────

PACKAGES = {
    "starter": {"name": "STARTER", "price": 29000, "quota": 25, "max_scrolls": 10},
    "basic":   {"name": "BASIC",   "price": 79000, "quota": 100, "max_scrolls": 20},
    "pro":     {"name": "PRO",     "price": 179000, "quota": 300, "max_scrolls": 40},
    "bisnis":  {"name": "BISNIS",  "price": 349000, "quota": 1000, "max_scrolls": 50},
}


def make_signature(merchant_code: str, amount: int, merchant_order_id: str) -> str:
    """MD5(merchantCode + amount + merchantOrderId + apiKey)"""
    raw = f"{merchant_code}{amount}{merchant_order_id}{DUITKU_API_KEY}"
    return hashlib.md5(raw.encode()).hexdigest()


def verify_callback_signature(
    merchant_code: str,
    amount: str,
    merchant_order_id: str,
    signature: str,
) -> bool:
    expected = make_signature(merchant_code, int(amount), merchant_order_id)
    return signature == expected


async def create_invoice(
    package_key: str,
    email: str,
    merchant_order_id: str,
) -> dict:
    """Hit Duitku v2/inquiry, return {paymentUrl, reference, ...}."""
    pkg = PACKAGES.get(package_key)
    if not pkg:
        raise ValueError(f"Unknown package: {package_key}")

    amount = pkg["price"]
    signature = make_signature(DUITKU_MERCHANT_CODE, amount, merchant_order_id)

    payload = {
        "merchantCode": DUITKU_MERCHANT_CODE,
        "paymentAmount": amount,
        "paymentMethod": "VC",  # General — user pilih sendiri di halaman Duitku
        "merchantOrderId": merchant_order_id,
        "productDetails": f"GMaps Scraper — {pkg['name']} ({pkg['quota']} pencarian)",
        "email": email,
        "customerVaName": email.split("@")[0],
        "callbackUrl": CALLBACK_URL,
        "returnUrl": RETURN_URL,
        "signature": signature,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API_URL}/v2/inquiry",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        data = resp.json()
        if resp.status_code != 200 or data.get("statusCode") != "00":
            raise Exception(f"Duitku error: {data.get('Message', data)}")
        return {
            "paymentUrl": data.get("paymentUrl"),
            "reference": data.get("reference"),
            "merchantOrderId": merchant_order_id,
        }
