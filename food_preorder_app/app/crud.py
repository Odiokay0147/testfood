from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta
import uuid

import app.models as models
import app.schemas as schemas
from app.auth import hash_password, verify_password


# ─────────────────────────────────────────────
# DEPOSIT RATE BY SCHEDULE TYPE
# ─────────────────────────────────────────────
DEPOSIT_RATES = {
    "hourly": 0.30,   # 30% for same-day / hourly bookings
    "daily":  0.40,   # 40% for next-day bookings
    "weekly": 0.50,   # 50% for weekly plans
}


def _generate_order_ref() -> str:
    ts = datetime.utcnow().strftime("%y%m%d%H%M")
    uid = uuid.uuid4().hex[:4].upper()
    return f"PG-{ts}-{uid}"


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    db_user = models.User(
        name=user.name,
        email=user.email,
        phone=user.phone,
        password=hash_password(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.password):
        return None
    return user


def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


# ─────────────────────────────────────────────
# VENDORS
# ─────────────────────────────────────────────
def get_all_vendors(db: Session):
    return db.query(models.Vendor).filter(models.Vendor.is_active == True).all()


def get_vendor(db: Session, vendor_id: int):
    vendor = db.query(models.Vendor).filter(models.Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


def get_vendor_menu(db: Session, vendor_id: int):
    get_vendor(db, vendor_id)   # raises 404 if missing
    return (
        db.query(models.Meal)
        .filter(models.Meal.vendor_id == vendor_id, models.Meal.is_available == True)
        .order_by(models.Meal.category, models.Meal.name)
        .all()
    )


# ─────────────────────────────────────────────
# ORDERS
# ─────────────────────────────────────────────

CHEFN_DISCOUNT_RATE = 0.10        # 10% discount
CHEFN_DISCOUNT_THRESHOLD = 10     # minimum total items to trigger order-level discount

def _apply_chefn_discounts(vendor_name: str, resolved_items: list) -> tuple:
    """
    Chef'N discount rules:
    1. Single meal with qty >= 10  → 10% off that meal's subtotal
    2. Total items across all meals >= 10 → 10% off the full order total

    Returns (final_total, resolved_items_with_discount, discount_applied, discount_amount, discount_reason)
    """
    if "chef" not in vendor_name.lower():
        # Not Chef'N — no discount
        raw_total = sum(subtotal for _, _, subtotal in resolved_items)
        return raw_total, resolved_items, False, 0.0, None

    total_qty = sum(qty for _, qty, _ in resolved_items)
    order_discount = total_qty >= CHEFN_DISCOUNT_THRESHOLD

    updated_items = []
    raw_total = 0.0
    discounted_total = 0.0

    for meal, qty, subtotal in resolved_items:
        item_discount = qty >= CHEFN_DISCOUNT_THRESHOLD
        if order_discount or item_discount:
            new_subtotal = round(subtotal * (1 - CHEFN_DISCOUNT_RATE), 2)
        else:
            new_subtotal = subtotal
        raw_total += subtotal
        discounted_total += new_subtotal
        updated_items.append((meal, qty, new_subtotal))

    discount_applied = discounted_total < raw_total
    discount_amount = round(raw_total - discounted_total, 2)

    if discount_applied:
        if order_discount:
            reason = f"10% discount — {total_qty} total items ordered"
        else:
            reason = "10% discount — single meal qty ≥ 10"
    else:
        reason = None

    return discounted_total, updated_items, discount_applied, discount_amount, reason


def create_order(db: Session, user_id: int, order: schemas.OrderCreate) -> models.Order:
    # validate vendor
    vendor = db.query(models.Vendor).filter(
        models.Vendor.id == order.vendor_id,
        models.Vendor.is_active == True
    ).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found or inactive")

    # resolve all meals
    resolved_items = []
    for item in order.items:
        meal = db.query(models.Meal).filter(
            models.Meal.id == item.meal_id,
            models.Meal.vendor_id == order.vendor_id,
            models.Meal.is_available == True
        ).first()
        if not meal:
            raise HTTPException(
                status_code=404,
                detail=f"Meal ID {item.meal_id} not found or unavailable for this vendor"
            )
        subtotal = meal.price * item.quantity
        resolved_items.append((meal, item.quantity, subtotal))

    # apply Chef'N discount rules
    total_price, resolved_items, discount_applied, discount_amount, discount_reason = \
        _apply_chefn_discounts(vendor.name, resolved_items)

    total_price = round(total_price, 2)

    # calculate deposit and balance
    if order.payment_type == "full":
        deposit_amount = total_price
        balance_due = 0.0
    else:
        rate = DEPOSIT_RATES[order.schedule_type]
        deposit_amount = round(total_price * rate, 2)
        balance_due = round(total_price - deposit_amount, 2)

    # build notes — append discount info
    notes = order.notes or ""
    if discount_applied:
        notes = f"[DISCOUNT: {discount_reason} — ₦{discount_amount:,.0f} saved] " + notes

    # create order
    db_order = models.Order(
        order_ref=_generate_order_ref(),
        user_id=user_id,
        vendor_id=order.vendor_id,
        total_price=total_price,
        deposit_amount=deposit_amount,
        balance_due=balance_due,
        payment_type=order.payment_type,
        schedule_type=order.schedule_type,
        delivery_date=order.delivery_date,
        delivery_time=order.delivery_time,
        notes=notes.strip(),
        discount_applied=discount_applied,
        discount_amount=discount_amount,
    )
    db.add(db_order)
    db.flush()

    # create order items
    for meal, qty, subtotal in resolved_items:
        db_item = models.OrderItem(
            order_id=db_order.id,
            meal_id=meal.id,
            quantity=qty,
            unit_price=meal.price,
            subtotal=subtotal,
        )
        db.add(db_item)

    db.commit()
    db.refresh(db_order)
    return db_order


def get_order_by_ref(db: Session, order_ref: str) -> models.Order:
    order = db.query(models.Order).filter(models.Order.order_ref == order_ref).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def get_orders_for_user(db: Session, user_id: int):
    return (
        db.query(models.Order)
        .filter(models.Order.user_id == user_id)
        .order_by(models.Order.created_at.desc())
        .all()
    )


def get_orders_for_vendor(db: Session, vendor_id: int, status: str = None, date: str = None):
    q = db.query(models.Order).filter(models.Order.vendor_id == vendor_id)
    if status:
        q = q.filter(models.Order.status == status)
    if date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            q = q.filter(
                models.Order.delivery_date >= d,
                models.Order.delivery_date < d + timedelta(days=1)
            )
        except ValueError:
            raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")
    return q.order_by(models.Order.delivery_date).all()


def update_order_status(db: Session, order_ref: str, new_status: str) -> models.Order:
    order = get_order_by_ref(db, order_ref)

    valid_transitions = {
        "pending":    ["confirmed", "cancelled"],
        "confirmed":  ["dispatched", "cancelled"],
        "dispatched": ["delivered"],
        "delivered":  [],
        "cancelled":  [],
    }
    if new_status not in valid_transitions.get(order.status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot move from '{order.status}' to '{new_status}'. "
                   f"Allowed: {valid_transitions[order.status]}"
        )

    order.status = new_status
    db.commit()
    db.refresh(order)
    return order


# ─────────────────────────────────────────────
# PAYMENTS
# ─────────────────────────────────────────────
def record_payment(db: Session, data: schemas.PaymentCreate, user_id: int) -> models.Payment:
    order = db.query(models.Order).filter(models.Order.id == data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # ownership check — only the order owner can pay
    if order.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your order")

    # prevent overpayment
    if data.payment_type == "deposit":
        if order.deposit_paid:
            raise HTTPException(400, "Deposit already paid for this order")
        expected = order.deposit_amount
        if abs(data.amount - expected) > 1.0:   # 1 Naira tolerance for float precision
            raise HTTPException(
                400,
                f"Deposit amount mismatch. Expected ₦{expected:.2f}, got ₦{data.amount:.2f}"
            )

    elif data.payment_type == "balance":
        if order.balance_paid:
            raise HTTPException(400, "Balance already paid for this order")
        if not order.deposit_paid:
            raise HTTPException(400, "Deposit must be paid before balance")
        expected = order.balance_due
        if abs(data.amount - expected) > 1.0:   # 1 Naira tolerance
            raise HTTPException(
                400,
                f"Balance amount mismatch. Expected ₦{expected:.2f}, got ₦{data.amount:.2f}"
            )

    elif data.payment_type == "full":
        if order.deposit_paid or order.balance_paid:
            raise HTTPException(400, "Order has already been paid")
        if order.payment_type != "full":
            raise HTTPException(400, "This order was not set up for full payment")

    # record payment
    payment = models.Payment(
        order_id=order.id,
        amount=data.amount,
        payment_type=data.payment_type,
        method=data.method,
        reference=data.reference,
        status="completed",
    )
    db.add(payment)

    # update order flags and status
    if data.payment_type == "deposit":
        order.deposit_paid = True
        order.status = "confirmed"
    elif data.payment_type == "balance":
        order.balance_paid = True
        # ready for dispatch once balance is cleared
    elif data.payment_type == "full":
        order.deposit_paid = True
        order.balance_paid = True
        order.status = "confirmed"

    db.commit()
    db.refresh(payment)
    return payment


def get_payments_for_order(db: Session, order_id: int):
    return db.query(models.Payment).filter(models.Payment.order_id == order_id).all()


# ─────────────────────────────────────────────
# REMINDERS
# ─────────────────────────────────────────────
def get_pending_balance_reminders(db: Session):
    """
    Returns orders whose delivery is tomorrow, deposit was paid,
    but balance has NOT been paid yet, and reminder hasn't been sent.
    """
    tomorrow_start = datetime.utcnow().replace(hour=0, minute=0, second=0) + timedelta(days=1)
    tomorrow_end = tomorrow_start + timedelta(days=1)

    return (
        db.query(models.Order)
        .filter(
            models.Order.delivery_date >= tomorrow_start,
            models.Order.delivery_date < tomorrow_end,
            models.Order.payment_type == "deposit",
            models.Order.deposit_paid == True,
            models.Order.balance_paid == False,
            models.Order.reminder_sent == False,
            models.Order.status == "confirmed",
        )
        .all()
    )


def mark_reminder_sent(db: Session, order: models.Order) -> models.Reminder:
    msg = (
        f"Hi {order.user.name}! Your order {order.order_ref} is scheduled for tomorrow. "
        f"Please complete your balance payment of GHS {order.balance_due:.2f} "
        f"before dispatch. Thank you for choosing us! 🙏"
    )
    reminder = models.Reminder(
        order_id=order.id,
        reminder_type="balance_reminder",
        message=msg,
    )
    db.add(reminder)
    order.reminder_sent = True
    db.commit()
    db.refresh(reminder)
    return reminder


# ─────────────────────────────────────────────
# DASHBOARD STATS
# ─────────────────────────────────────────────
def get_dashboard_stats(db: Session, vendor_id: int = None):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    q = db.query(models.Order)
    if vendor_id:
        q = q.filter(models.Order.vendor_id == vendor_id)

    all_orders = q.all()
    today_orders = [o for o in all_orders if today_start <= o.delivery_date < today_end]
    confirmed = [o for o in all_orders if o.status in ("confirmed", "dispatched", "delivered")]
    pending_balance = [
        o for o in all_orders
        if o.payment_type == "deposit" and o.deposit_paid and not o.balance_paid
    ]

    by_schedule = {"hourly": 0, "daily": 0, "weekly": 0}
    for o in all_orders:
        if o.schedule_type in by_schedule:
            by_schedule[o.schedule_type] += 1

    return {
        "total_orders": len(all_orders),
        "today_orders": len(today_orders),
        "confirmed_orders": len(confirmed),
        "total_revenue": round(sum(o.total_price for o in confirmed), 2),
        "pending_balance_count": len(pending_balance),
        "pending_balance_value": round(sum(o.balance_due for o in pending_balance), 2),
        "orders_by_schedule": by_schedule,
    }