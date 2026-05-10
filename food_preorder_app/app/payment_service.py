"""
payment_service.py
All Paystack integration logic — initialize, verify, webhook.
"""

import os
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

PAYSTACK_SECRET_KEY  = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY  = os.getenv("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_BASE_URL    = "https://api.paystack.co"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────
# INITIALIZE A TRANSACTION
# ─────────────────────────────────────────────
def initialize_transaction(
    email: str,
    amount_naira: float,
    order_ref: str,
    payment_type: str,          # "deposit" | "balance" | "full"
    callback_url: str = None,
    customer_name: str = None,
) -> dict:
    """
    Create a Paystack transaction. Returns authorization_url for redirect
    and access_code for the inline popup.

    Amount is in Naira — we convert to kobo internally.
    """
    amount_kobo = int(round(amount_naira * 100))

    payload = {
        "email": email,
        "amount": amount_kobo,
        "reference": f"{order_ref}-{payment_type}-{_short_uid()}",
        "currency": "NGN",
        "channels": ["card", "bank_transfer", "ussd"],
        "metadata": {
            "order_ref": order_ref,
            "payment_type": payment_type,
            "customer_name": customer_name or "",
            "cancel_action": callback_url or "",
        },
    }

    if callback_url:
        payload["callback_url"] = callback_url

    resp = requests.post(
        f"{PAYSTACK_BASE_URL}/transaction/initialize",
        json=payload,
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("status"):
        raise ValueError(f"Paystack error: {data.get('message', 'Unknown error')}")

    return {
        "authorization_url": data["data"]["authorization_url"],
        "access_code":       data["data"]["access_code"],
        "reference":         data["data"]["reference"],
    }


# ─────────────────────────────────────────────
# VERIFY A TRANSACTION
# ─────────────────────────────────────────────
def verify_transaction(reference: str) -> dict:
    """
    Verify a transaction by reference. Returns full transaction data.
    Raises ValueError if payment failed or amount mismatch.
    """
    resp = requests.get(
        f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("status"):
        raise ValueError(f"Paystack verify error: {data.get('message')}")

    tx = data["data"]
    return {
        "reference":    tx["reference"],
        "status":       tx["status"],           # success | failed | abandoned
        "amount_naira": tx["amount"] / 100,     # convert kobo → naira
        "currency":     tx["currency"],
        "channel":      tx["channel"],          # card | bank_transfer | ussd
        "paid_at":      tx.get("paid_at"),
        "customer_email": tx["customer"]["email"],
        "metadata":     tx.get("metadata", {}),
        "gateway_response": tx.get("gateway_response", ""),
    }


# ─────────────────────────────────────────────
# VERIFY WEBHOOK SIGNATURE
# ─────────────────────────────────────────────
def verify_webhook_signature(payload_bytes: bytes, signature: str) -> bool:
    """
    Verify that a webhook request came from Paystack.
    signature is from the X-Paystack-Signature header.
    """
    expected = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload_bytes,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _short_uid() -> str:
    import uuid
    return uuid.uuid4().hex[:8].upper()


def get_public_key() -> str:
    return PAYSTACK_PUBLIC_KEY