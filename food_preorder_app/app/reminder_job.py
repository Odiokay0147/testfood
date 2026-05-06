"""
reminder_job.py
APScheduler-based daily job that:
1. Finds all orders due tomorrow with unpaid balance
2. Sends WhatsApp reminders to each customer
3. Logs the reminder in the database

Schedule: runs every day at 9:00 AM server time.
Can also be triggered manually via POST /reminders/run
"""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
import app.models as models
from app.notifier import send_balance_reminder

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_balance_reminders():
    """
    Core reminder logic. Queries DB for eligible orders and sends WhatsApp messages.
    Returns a summary dict for logging/API response.
    """
    db = SessionLocal()
    results = {"sent": [], "failed": [], "total_eligible": 0}

    try:
        tomorrow_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        tomorrow_end   = tomorrow_start + timedelta(days=1)

        eligible_orders = (
            db.query(models.Order)
            .filter(
                models.Order.delivery_date >= tomorrow_start,
                models.Order.delivery_date < tomorrow_end,
                models.Order.payment_type  == "deposit",
                models.Order.deposit_paid  == True,
                models.Order.balance_paid  == False,
                models.Order.reminder_sent == False,
                models.Order.status        == "confirmed",
            )
            .all()
        )

        results["total_eligible"] = len(eligible_orders)
        logger.info(f"[Reminders] Found {len(eligible_orders)} orders due tomorrow with unpaid balance.")

        for order in eligible_orders:
            customer = order.user
            vendor   = order.vendor

            delivery_date = order.delivery_date.strftime("%d %b %Y")
            delivery_time = order.delivery_time or "your scheduled time"

            result = send_balance_reminder(
                customer_name=customer.name,
                phone=customer.phone if hasattr(customer, "phone") and customer.phone else None,
                order_ref=order.order_ref,
                balance_due=order.balance_due,
                delivery_date=delivery_date,
                delivery_time=delivery_time,
                vendor_name=vendor.name,
            )

            if result["success"]:
                # Mark reminder sent in DB
                order.reminder_sent = True
                reminder_log = models.Reminder(
                    order_id=order.id,
                    reminder_type="balance_reminder",
                    message=(
                        f"WhatsApp balance reminder sent to {customer.name} "
                        f"for order {order.order_ref}. "
                        f"Balance: GHS {order.balance_due:.2f}. "
                        f"SID: {result.get('message_sid', 'N/A')}"
                    ),
                )
                db.add(reminder_log)
                results["sent"].append({
                    "order_ref": order.order_ref,
                    "customer": customer.name,
                    "message_sid": result.get("message_sid"),
                })
                logger.info(f"[Reminders] ✅ Sent to {customer.name} — {order.order_ref}")
            else:
                results["failed"].append({
                    "order_ref": order.order_ref,
                    "customer": customer.name,
                    "error": result.get("error"),
                })
                logger.warning(
                    f"[Reminders] ❌ Failed for {customer.name} — {order.order_ref}: {result.get('error')}"
                )

        db.commit()

    except Exception as e:
        logger.error(f"[Reminders] Job crashed: {e}")
        results["error"] = str(e)
    finally:
        db.close()

    logger.info(
        f"[Reminders] Done. Sent: {len(results['sent'])} | Failed: {len(results['failed'])}"
    )
    return results


# ─────────────────────────────────────────────
# SCHEDULER SETUP
# ─────────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="Africa/Lagos")


def start_scheduler():
    """
    Start the background scheduler.
    Called once on app startup.
    Runs reminder job every day at 9:00 AM (Africa/Lagos timezone).
    """
    if not scheduler.running:
        scheduler.add_job(
            func=run_balance_reminders,
            trigger=CronTrigger(hour=9, minute=0),
            id="daily_balance_reminder",
            name="Daily Balance Reminder — 9AM",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("⏰ Reminder scheduler started — runs daily at 9:00 AM (Lagos time)")


def stop_scheduler():
    """Gracefully shut down scheduler on app exit."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("⏰ Reminder scheduler stopped")