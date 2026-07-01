"""Duitku API wrapper — inquiry, callback verification, signature (HMAC-SHA256)."""

import os
import json
import hashlib
import hmac
import httpx
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────

DUITKU_MERCHANT_CODE = os.environ.get("DUITKU_MERCHANT_CODE", "DSXXXX")
DUITKU_API_KEY = os.environ.get("DUITKU_API_KEY", "xxxxxxxx")
DUITKU_SANDBOX = os.environ.get("DUITKU_SANDBOX", "true").lower() == "true"

SANDBOX_URL = "https://sandbox.duitku.com/webapi/api/merchant"
PRODUCTION_URL = "https://passport.duitku.com/webapi/api/merchant"
API_URL = SANDBOX_URL if DUITKU_SANDBOX else PRODUCTION_URL

CALLBACK_URL = os.environ.get("CALLBACK_URL", "https://domainkamu.com/api/payment/callback")
RETURN_URL = os.environ.get("RETURN_URL", "https://domainkamu.com/dashboard")

# ── Package Pricing ─────────────────────────────────────────────────

# Default PACKAGES — fallback kalau packages.json belum ada
_DEFAULT_PACKAGES = {
    "starter": {"name": "STARTER", "price": 25000, "quota": 50, "max_scrolls": 10},
    "basic":   {"name": "BASIC",   "price": 69000, "quota": 200, "max_scrolls": 20},
    "pro":     {"name": "PRO",     "price": 149000, "quota": 500, "max_scrolls": 40},
    "bisnis":  {"name": "BISNIS",  "price": 299000, "quota": 1500, "max_scrolls": 50},
}

PACKAGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages.json")

def _load_packages() -> dict:
    """Load packages from JSON file, fallback ke default."""
    try:
        if os.path.exists(PACKAGES_FILE):
            with open(PACKAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and len(data) > 0:
                    print(f"   [PACKAGES] Loaded from {PACKAGES_FILE}")
                    return data
    except Exception as e:
        print(f"   [PACKAGES] Failed to load {PACKAGES_FILE}: {e}, using defaults")
    return dict(_DEFAULT_PACKAGES)

def _save_packages(data: dict) -> None:
    """Save packages to JSON file."""
    with open(PACKAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"   [PACKAGES] Saved to {PACKAGES_FILE}")

# Load at module import
PACKAGES = _load_packages()

# ── HMAC-SHA256 Signatures ──────────────────────────────────────────

def _hmac_sign(payload: str) -> str:
    """HMAC-SHA256 hex lowercase."""
    return hmac.new(DUITKU_API_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_payment_method_signature(amount: int) -> str:
    """Signature untuk getPaymentMethod: merchantCode + amount + datetime."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return _hmac_sign(f"{DUITKU_MERCHANT_CODE}{amount}{now}"), now


def make_inquiry_signature(merchant_order_id: str, amount: int) -> str:
    """Signature untuk inquiry: merchantCode + merchantOrderId + paymentAmount."""
    return _hmac_sign(f"{DUITKU_MERCHANT_CODE}{merchant_order_id}{amount}")


def verify_callback_signature(merchant_code: str, amount: int, merchant_order_id: str, signature: str) -> bool:
    """Verify callback signature: merchantCode + amount + merchantOrderId."""
    expected = _hmac_sign(f"{merchant_code}{amount}{merchant_order_id}")
    return hmac.compare_digest(signature, expected)


# ── API Calls ───────────────────────────────────────────────────────

async def create_invoice(
    package_key: str,
    email: str,
    merchant_order_id: str,
    customer_name: str = "",
    payment_method: str = "VC",
) -> dict:
    """Create payment invoice via Duitku v2/inquiry."""
    pkg = PACKAGES.get(package_key)
    if not pkg:
        raise ValueError(f"Unknown package: {package_key}")

    amount = pkg["price"]
    product_name = f"GMaps Scraper — {pkg['name']} ({pkg['quota']} pencarian, {pkg['max_scrolls']} scroll)"
    customer_va_name = (customer_name or email.split("@")[0])[:20]

    signature = make_inquiry_signature(merchant_order_id, amount)

    payload = {
        "merchantCode": DUITKU_MERCHANT_CODE,
        "paymentAmount": amount,
        "paymentMethod": payment_method,
        "merchantOrderId": merchant_order_id,
        "productDetails": product_name[:255],
        "email": email,
        "customerVaName": customer_va_name,
        "callbackUrl": CALLBACK_URL,
        "returnUrl": RETURN_URL,
        "signature": signature,
        "expiryPeriod": 1440,  # 24 jam
        "itemDetails": [{
            "name": product_name[:255],
            "price": amount,
            "quantity": 1,
        }],
        "customerDetail": {
            "firstName": customer_va_name[:20],
            "lastName": "",
            "email": email,
            "billingAddress": {
                "firstName": customer_va_name[:20],
                "lastName": "",
                "address": "-",
                "city": "-",
                "postalCode": "-",
                "countryCode": "ID",
            },
            "shippingAddress": {
                "firstName": customer_va_name[:20],
                "lastName": "",
                "address": "-",
                "city": "-",
                "postalCode": "-",
                "countryCode": "ID",
            },
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API_URL}/v2/inquiry",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        data = resp.json()
        if resp.status_code != 200 or data.get("statusCode") != "00":
            err_msg = data.get("statusMessage") or data.get("Message") or str(data)
            raise Exception(f"Duitku error: {err_msg}")
        return {
            "paymentUrl": data.get("paymentUrl"),
            "reference": data.get("reference"),
            "vaNumber": data.get("vaNumber"),
            "amount": data.get("amount"),
            "merchantOrderId": merchant_order_id,
        }


async def get_payment_methods(amount: int = 10000) -> list:
    """Ambil daftar metode pembayaran yang aktif."""
    signature, dt = make_payment_method_signature(amount)

    payload = {
        "merchantcode": DUITKU_MERCHANT_CODE,
        "amount": amount,
        "datetime": dt,
        "signature": signature,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/paymentmethod/getpaymentmethod",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        data = resp.json()
        if data.get("responseCode") != "00":
            err_msg = data.get("responseMessage") or str(data)
            raise Exception(f"Duitku get payment methods error: {err_msg}")
        return data.get("paymentFee", [])


async def check_transaction(merchant_order_id: str) -> dict:
    """Cek status transaksi."""
    signature = _hmac_sign(f"{DUITKU_MERCHANT_CODE}{merchant_order_id}")

    params = {
        "merchantCode": DUITKU_MERCHANT_CODE,
        "merchantOrderId": merchant_order_id,
        "signature": signature,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/transactionStatus",
            json=params,
            headers={"Content-Type": "application/json"},
        )
        return resp.json()
