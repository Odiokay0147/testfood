from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional
import os

from app.database import SessionLocal, engine
import app.models as models
import app.schemas as schemas
import app.crud as crud
from app.auth import create_access_token, SECRET_KEY, ALGORITHM
from app.notifier import send_order_confirmation, send_deposit_receipt, send_dispatch_notification
from app.reminder_job import start_scheduler, stop_scheduler, run_balance_reminders

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Prep & Go — Food Pre-Order API", version="2.0.0")

bearer_scheme = HTTPBearer()

# Serve frontend HTML
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/app", include_in_schema=False)
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ─────────────────────────────────────────────
# DEPENDENCIES
# ─────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Decode JWT and return the logged-in user. Raises 401 if invalid."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


# ─────────────────────────────────────────────
# STARTUP — SEED VENDORS & MEALS
# ─────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    db = SessionLocal()

    if not db.query(models.Vendor).first():
        # Vendor 1 — Chaf'N
        chafn = models.Vendor(
            name="Chaf'N",
            description="Home-cooked meals with authentic local flavours. Freshly prepared daily.",
            phone="+233200000001",
        )
        db.add(chafn)
        db.flush()

        for meal_data in [
            ("Jollof Rice & Chicken", "Party jollof with grilled chicken and plantain", 35.00, "Rice Dishes"),
            ("Banku & Tilapia",        "Fermented corn dough with grilled tilapia & pepper sauce", 40.00, "Local Favourites"),
            ("Waakye Special",         "Rice and beans with spaghetti, wele, eggs, and shito", 30.00, "Rice Dishes"),
            ("Fufu & Light Soup",      "Pounded fufu with aromatic light soup, choice of protein", 38.00, "Soups & Stews"),
            ("Kontomire Stew & Rice",  "Spinach stew with smoked fish and steamed rice", 28.00, "Soups & Stews"),
        ]:
            db.add(models.Meal(
                name=meal_data[0], description=meal_data[1],
                price=meal_data[2], category=meal_data[3], vendor_id=chafn.id
            ))

        # Vendor 2 — Ur Cravings Crunches
        ucc = models.Vendor(
            name="Ur Cravings Crunches",
            description="Street-style bites and crunchy favourites. Satisfying every craving.",
            phone="+233200000002",
        )
        db.add(ucc)
        db.flush()

        for meal_data in [
            ("Crispy Chicken Burger", "Double-stacked crispy chicken with house sauce", 45.00, "Burgers"),
            ("Loaded Fries Box",      "Large fries with cheese sauce, jalapeños, chicken bits", 30.00, "Sides"),
            ("Spicy Wings (6pc)",     "Buffalo wings with blue cheese dip", 38.00, "Chicken"),
            ("Shawarma Wrap",         "Grilled chicken or beef with garlic sauce", 35.00, "Wraps"),
            ("Fish & Chips",          "Golden battered tilapia with chunky fries", 40.00, "Mains"),
        ]:
            db.add(models.Meal(
                name=meal_data[0], description=meal_data[1],
                price=meal_data[2], category=meal_data[3], vendor_id=ucc.id
            ))

        db.commit()
        print("✅ Seed data created — 2 vendors, 10 meals")

    db.close()

    # Start the daily reminder scheduler
    start_scheduler()


@app.on_event("shutdown")
def shutdown_event():
    stop_scheduler()


# ─────────────────────────────────────────────
# ROOT
# ─────────────────────────────────────────────
@app.get("/")
def home():
    return {
        "app": "Prep & Go Food Pre-Order API",
        "version": "2.0.0",
        "docs": "/docs",
    }


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
@app.post("/signup", response_model=schemas.UserOut, status_code=201)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, user)


@app.post("/login")
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = crud.authenticate_user(db, user.email, user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"user_id": db_user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": db_user.id, "name": db_user.name, "email": db_user.email},
    }


# ─────────────────────────────────────────────
# VENDORS
# ─────────────────────────────────────────────
@app.get("/vendors", response_model=list[schemas.VendorOut])
def list_vendors(db: Session = Depends(get_db)):
    """Browse all active vendors and their menus."""
    return crud.get_all_vendors(db)


@app.get("/vendors/{vendor_id}", response_model=schemas.VendorOut)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    return crud.get_vendor(db, vendor_id)


@app.get("/vendors/{vendor_id}/menu", response_model=list[schemas.MealOut])
def vendor_menu(vendor_id: int, db: Session = Depends(get_db)):
    """List available meals for a vendor."""
    return crud.get_vendor_menu(db, vendor_id)


# ─────────────────────────────────────────────
# ORDERS  (protected — must be logged in)
# ─────────────────────────────────────────────
@app.post("/orders", response_model=schemas.OrderOut, status_code=201)
def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Place a new order. Supports multiple items, hourly/daily/weekly scheduling,
    and deposit or full-payment options.

    Deposit rates:
    - hourly → 30%
    - daily  → 40%
    - weekly → 50%
    """
    new_order = crud.create_order(db, current_user.id, order)

    # Send WhatsApp order confirmation if customer has a phone number
    if current_user.phone:
        vendor = db.query(models.Vendor).filter(models.Vendor.id == order.vendor_id).first()
        send_order_confirmation(
            customer_name=current_user.name,
            phone=current_user.phone,
            order_ref=new_order.order_ref,
            total=new_order.total_price,
            deposit=new_order.deposit_amount,
            balance=new_order.balance_due,
            vendor_name=vendor.name if vendor else "your vendor",
            delivery_date=new_order.delivery_date.strftime("%d %b %Y"),
            delivery_time=new_order.delivery_time or "TBD",
            schedule_type=new_order.schedule_type,
        )

    return new_order


@app.get("/orders/my", response_model=list[schemas.OrderOut])
def my_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Fetch all orders for the logged-in customer."""
    return crud.get_orders_for_user(db, current_user.id)


@app.get("/orders/{order_ref}", response_model=schemas.OrderOut)
def get_order(
    order_ref: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = crud.get_order_by_ref(db, order_ref)
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return order


@app.patch("/orders/{order_ref}/status")
def update_status(
    order_ref: str,
    body: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Update order status. Follows valid transitions only:
    pending → confirmed → dispatched → delivered
    Any stage → cancelled
    """
    return crud.update_order_status(db, order_ref, body.status)


# ─────────────────────────────────────────────
# VENDOR ORDER VIEW  (vendor sees their orders)
# ─────────────────────────────────────────────
@app.get("/vendors/{vendor_id}/orders")
def vendor_orders(
    vendor_id: int,
    status: Optional[str] = None,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Vendor dashboard — list orders for a specific vendor.
    Filter by ?status=confirmed or ?date=2025-06-01
    """
    return crud.get_orders_for_vendor(db, vendor_id, status, date)


# ─────────────────────────────────────────────
# PAYMENTS  (protected)
# ─────────────────────────────────────────────
@app.post("/payments", status_code=201)
def make_payment(
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Record a payment. System validates:
    - Correct amount for deposit or balance
    - Deposit must come before balance
    - No double payments
    - Only the order owner can pay
    """
    result = crud.record_payment(db, payment, current_user.id)
    order = db.query(models.Order).filter(models.Order.id == payment.order_id).first()

    # Send WhatsApp receipt if customer has a phone number
    if current_user.phone:
        if payment.payment_type == "deposit":
            send_deposit_receipt(
                customer_name=current_user.name,
                phone=current_user.phone,
                order_ref=order.order_ref,
                amount=payment.amount,
                balance_due=order.balance_due,
                vendor_name=order.vendor.name,
            )
        elif payment.payment_type == "balance" and order.status == "confirmed":
            send_dispatch_notification(
                customer_name=current_user.name,
                phone=current_user.phone,
                order_ref=order.order_ref,
                vendor_name=order.vendor.name,
                delivery_time=order.delivery_time or "your scheduled time",
            )

    return {
        "payment": result,
        "order_ref": order.order_ref,
        "order_status": order.status,
        "balance_remaining": order.balance_due if not order.balance_paid else 0.0,
        "message": "Payment recorded successfully ✅",
    }


@app.get("/orders/{order_ref}/payments")
def order_payments(
    order_ref: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """View full payment history for an order."""
    order = crud.get_order_by_ref(db, order_ref)
    if order.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return crud.get_payments_for_order(db, order.id)


# ─────────────────────────────────────────────
# REMINDERS
# ─────────────────────────────────────────────
@app.get("/reminders/pending")
def pending_reminders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Returns all orders due tomorrow that still have an unpaid balance.
    Run this daily (e.g. via cron) to trigger reminder messages.
    """
    orders = crud.get_pending_balance_reminders(db)
    return {
        "count": len(orders),
        "orders": [
            {
                "order_ref": o.order_ref,
                "customer_name": o.user.name,
                "balance_due": o.balance_due,
                "delivery_date": o.delivery_date.strftime("%Y-%m-%d"),
                "delivery_time": o.delivery_time,
                "vendor": o.vendor.name,
                "reminder_message": (
                    f"Hi {o.user.name}! Your order {o.order_ref} is due tomorrow. "
                    f"Please pay your balance of GHS {o.balance_due:.2f} before dispatch."
                ),
            }
            for o in orders
        ],
    }


@app.post("/reminders/send/{order_ref}")
def send_reminder(
    order_ref: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Send a WhatsApp balance reminder for a specific order and log it."""
    order = crud.get_order_by_ref(db, order_ref)

    # Send actual WhatsApp message
    wa_result = None
    if order.user.phone:
        from app.notifier import send_balance_reminder
        wa_result = send_balance_reminder(
            customer_name=order.user.name,
            phone=order.user.phone,
            order_ref=order.order_ref,
            balance_due=order.balance_due,
            delivery_date=order.delivery_date.strftime("%d %b %Y"),
            delivery_time=order.delivery_time or "your scheduled time",
            vendor_name=order.vendor.name,
        )

    reminder = crud.mark_reminder_sent(db, order)
    return {
        "message": "Reminder sent and logged",
        "order_ref": order_ref,
        "whatsapp": wa_result,
        "reminder_message": reminder.message,
        "sent_at": reminder.sent_at,
    }


@app.post("/reminders/run")
def run_reminders_now(
    current_user: models.User = Depends(get_current_user),
):
    """
    Manually trigger the daily reminder job immediately.
    Useful for testing or if the scheduler missed a run.
    Normally this runs automatically every day at 9:00 AM.
    """
    results = run_balance_reminders()
    return {
        "message": "Reminder job completed",
        "total_eligible": results["total_eligible"],
        "sent": len(results["sent"]),
        "failed": len(results["failed"]),
        "details": results,
    }


# ─────────────────────────────────────────────
# DASHBOARD STATS
# ─────────────────────────────────────────────
@app.get("/dashboard")
def dashboard(
    vendor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Overall or per-vendor stats. Pass ?vendor_id=1 to filter."""
    return crud.get_dashboard_stats(db, vendor_id)


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)