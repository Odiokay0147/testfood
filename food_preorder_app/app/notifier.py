"""
notifier.py
Sends WhatsApp messages to customers via Twilio.
All functions return a result dict so callers can log success/failure.
"""

import os
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox default


def _get_client():
    from twilio.rest import Client
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise EnvironmentError(
            "Twilio credentials missing. "
            "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in your .env file."
        )
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _format_phone(phone: str) -> str:
    """
    Ensure phone is in WhatsApp format: whatsapp:+XXXXXXXXXXX
    Accepts: +234XXXXXXXXX, 0XXXXXXXXX (Nigeria)
    """
    phone = phone.strip().replace(" ", "").replace("-", "")

    # Already formatted
    if phone.startswith("whatsapp:"):
        return phone

    # Add country code if local format (starts with 0)
    if phone.startswith("0"):
        # Default to Nigeria (+234)
        phone = "+234" + phone[1:]

    # Ensure + prefix
    if not phone.startswith("+"):
        phone = "+" + phone

    return f"whatsapp:{phone}"


def send_whatsapp(to_phone: str, message: str) -> dict:
    """
    Send a WhatsApp message to a customer.
    Returns a result dict with status and message_sid or error.
    """
    try:
        client = _get_client()
        msg = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=_format_phone(to_phone),
            body=message,
        )
        return {
            "success": True,
            "message_sid": msg.sid,
            "to": to_phone,
            "status": msg.status,
        }
    except EnvironmentError as e:
        return {"success": False, "error": str(e), "to": to_phone}
    except Exception as e:
        return {"success": False, "error": str(e), "to": to_phone}


# ─────────────────────────────────────────────
# MESSAGE TEMPLATES
# ─────────────────────────────────────────────

def send_balance_reminder(customer_name: str, phone: str, order_ref: str,
                           balance_due: float, delivery_date: str,
                           delivery_time: str, vendor_name: str) -> dict:
    """
    Sent the day before delivery to customers with unpaid balance.
    """
    message = (
        f"👋 Hello {customer_name}!\n\n"
        f"Your order *{order_ref}* from *{vendor_name}* is scheduled for delivery tomorrow "
        f"({delivery_date} at {delivery_time or 'your chosen time'}).\n\n"
        f"💳 *Balance due:* NGN {balance_due:.2f}\n\n"
        f"Please complete your payment before dispatch so your order is not delayed. "
        f"Thank you for choosing Prep & Go! 🙏"
    )
    return send_whatsapp(phone, message)


def send_order_confirmation(customer_name: str, phone: str, order_ref: str,
                             total: float, deposit: float, balance: float,
                             vendor_name: str, delivery_date: str,
                             delivery_time: str, schedule_type: str) -> dict:
    """
    Sent immediately after an order is placed.
    """
    message = (
        f"✅ *Order Confirmed!*\n\n"
        f"Hi {customer_name}, your pre-order has been placed with *{vendor_name}*.\n\n"
        f"📋 *Order Ref:* {order_ref}\n"
        f"📅 *Delivery:* {delivery_date} at {delivery_time or 'TBD'}\n"
        f"🗓️ *Schedule:* {schedule_type.title()}\n\n"
        f"💰 *Total:* NGN {total:.2f}\n"
        f"💳 *Deposit to pay now:* NGN {deposit:.2f}\n"
        f"🔄 *Balance on delivery day:* NGN {balance:.2f}\n\n"
        f"Please pay your deposit to secure your order. "
        f"Reply to this message if you need help. 🍽️"
    )
    return send_whatsapp(phone, message)


def send_deposit_receipt(customer_name: str, phone: str, order_ref: str,
                          amount: float, balance_due: float, vendor_name: str) -> dict:
    """
    Sent after deposit is successfully recorded.
    """
    message = (
        f"🎉 *Deposit Received!*\n\n"
        f"Hi {customer_name}, we've received your deposit of *GHS {amount:.2f}* "
        f"for order *{order_ref}* with {vendor_name}.\n\n"
        f"Your order is now *confirmed* and secured! 🔒\n\n"
        f"📌 *Remaining balance:* NGN {balance_due:.2f} (due on delivery day)\n\n"
        f"We'll remind you the day before delivery. Thank you! 🙏"
    )
    return send_whatsapp(phone, message)


def send_dispatch_notification(customer_name: str, phone: str, order_ref: str,
                                vendor_name: str, delivery_time: str) -> dict:
    """
    Sent when vendor marks order as dispatched.
    """
    message = (
        f"🚀 *Your Order is On Its Way!*\n\n"
        f"Hi {customer_name}, your order *{order_ref}* from *{vendor_name}* "
        f"has been dispatched and is heading your way!\n\n"
        f"⏰ *Expected arrival:* {delivery_time or 'Soon'}\n\n"
        f"Please ensure your balance is ready for collection on delivery. "
        f"Enjoy your meal! 🍽️"
    )
    return send_whatsapp(phone, message)