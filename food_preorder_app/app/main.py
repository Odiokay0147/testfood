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
    _reseed_if_needed(db)
    db.close()
    start_scheduler()


def _reseed_if_needed(db):
    """Wipe and reseed vendors/meals. Safe to call on startup."""
    existing = db.query(models.Vendor).first()
    if existing and existing.name in ("Chaf'N", "Chef'N", "Ur Cravings Crunches"):
        # Already seeded with old data — wipe and redo
        db.query(models.OrderItem).delete()
        db.query(models.Order).delete()
        db.query(models.Meal).delete()
        db.query(models.Vendor).delete()
        db.commit()
        existing = None

    if not existing:
        # ── Vendor 1: Chef'N ──────────────────────────
        chefn = models.Vendor(
            name="Chef'N",
            description="Authentic Nigerian home cooking. Rich stews, jollof rice & more, freshly prepared daily.",
            phone="+2348000000001",
        )
        db.add(chefn)
        db.flush()

        chefn_meals = [
            ("Jollof Rice with Pepper Chicken & Plantain",         "Smoky party jollof, spiced pepper chicken & fried plantain",          5000, "Rice"),
            ("Jollof Rice with Pepper Chicken",                    "Classic smoky jollof with well-seasoned pepper chicken",              4500, "Rice"),
            ("Jollof Spaghetti with Chicken or Beef",              "Spicy jollof spaghetti with your choice of chicken or beef",          5000, "Pasta"),
            ("Ewa Agoyin with Plantain/Bread & Croaker Fish",      "Soft mashed beans in spiced Agoyin sauce, plantain/bread & fish",    5000, "Beans"),
            ("Mixed Rice (Jollof & Fried) with Pepper Chicken & Plantain", "Best of both worlds — jollof & fried rice combo with chicken & plantain", 5000, "Rice"),
            ("Mixed Rice (Jollof & Fried) with Pepper Chicken",   "Jollof & fried rice combo served with spiced pepper chicken",         4500, "Rice"),
            ("White Rice & Stew with Pepper Chicken & Plantain",  "Fluffy white rice in rich tomato stew, pepper chicken & plantain",    5000, "Rice"),
            ("White Rice & Stew with Pepper Chicken",             "Fluffy white rice in rich tomato stew with spiced pepper chicken",    4500, "Rice"),
            ("Jollof Rice with Big Beef & Plantain",              "Smoky jollof rice with a generous cut of seasoned beef & plantain",   5000, "Rice"),
        ]
        for name, desc, price, cat in chefn_meals:
            db.add(models.Meal(name=name, description=desc, price=price, category=cat, vendor_id=chefn.id))

        # ── Vendor 2: Ur Cravings Crunches ───────────
        ucc = models.Vendor(
            name="Ur Cravings Crunches",
            description="Crunchy snacks, fresh homemade drinks & small chops. Every craving sorted!",
            phone="+2348000000002",
        )
        db.add(ucc)
        db.flush()

        ucc_meals = [
            # Coated Peanuts — Jars
            ("Coated Peanuts — Big Jar",      "Crunchy coated peanuts in a big jar",    3500, "Snacks"),
            ("Coated Peanuts — Medium Jar",   "Crunchy coated peanuts in a medium jar", 2700, "Snacks"),
            ("Coated Peanuts — Small Jar",    "Crunchy coated peanuts in a small jar",  2000, "Snacks"),
            # Coated Peanuts — Ziplock
            ("Coated Peanuts — Big Pack",     "Coated peanuts in a big ziplock pack",   3000, "Snacks"),
            ("Coated Peanuts — Medium Pack",  "Coated peanuts in a medium ziplock pack",2400, "Snacks"),
            ("Coated Peanuts — Small Pack",   "Coated peanuts in a small ziplock pack", 1200, "Snacks"),
            ("Coated Peanuts — Mini Pack",    "Coated peanuts in a mini ziplock pack",   800, "Snacks"),
            # Chin-Chin — Jars
            ("Crunchy Chin-Chin — Big Jar",   "Homemade crunchy chin-chin in a big jar",   3000, "Snacks"),
            ("Crunchy Chin-Chin — Medium Jar","Homemade crunchy chin-chin in a medium jar", 2500, "Snacks"),
            ("Crunchy Chin-Chin — Small Jar", "Homemade crunchy chin-chin in a small jar",  1300, "Snacks"),
            # Chin-Chin — Ziplock
            ("Crunchy Chin-Chin — Big Pack",  "Chin-chin in a big ziplock pack",   2500, "Snacks"),
            ("Crunchy Chin-Chin — Medium Pack","Chin-chin in a medium ziplock pack",1300, "Snacks"),
            ("Crunchy Chin-Chin — Small Pack","Chin-chin in a small ziplock pack",  1000, "Snacks"),
            ("Crunchy Chin-Chin — Mini Pack", "Chin-chin in a mini ziplock pack",    500, "Snacks"),
            # Fresh Drinks
            ("Zobo Drink — Big Bottle (75cl)",    "Fresh homemade hibiscus zobo drink — 75cl", 1500, "Fresh Drinks"),
            ("Zobo Drink — Medium Bottle (50cl)", "Fresh homemade hibiscus zobo drink — 50cl", 1000, "Fresh Drinks"),
            ("Zobo Drink — Small Bottle (35cl)",  "Fresh homemade hibiscus zobo drink — 35cl",  500, "Fresh Drinks"),
            ("Tiger Nut Milk — Big Bottle",       "Creamy homemade tiger nut milk drink",       1500, "Fresh Drinks"),
            ("Tiger Nut Milk — Medium Bottle",    "Creamy homemade tiger nut milk drink",       1000, "Fresh Drinks"),
            ("Tiger Nut Milk — Small Bottle",     "Creamy homemade tiger nut milk drink",        500, "Fresh Drinks"),
            ("Coconut Heaven — Big Bottle",       "Refreshing homemade coconut drink",           1500, "Fresh Drinks"),
            ("Coconut Heaven — Medium Bottle",    "Refreshing homemade coconut drink",           1200, "Fresh Drinks"),
            ("Coconut Heaven — Small Bottle",     "Refreshing homemade coconut drink",            500, "Fresh Drinks"),
            # Small Chops / Bulk
            ("50 Beef Samosa",     "Crispy beef-filled samosas — bulk order of 50 pieces",    15000, "Small Chops"),
            ("50 Chicken Samosa",  "Crispy chicken-filled samosas — bulk order of 50 pieces", 15000, "Small Chops"),
            ("50 Spring Rolls",    "Golden crispy spring rolls — bulk order of 50 pieces",    13000, "Small Chops"),
            ("Puff Puff",          "Freshly fried soft puff puff — bulk order",               17000, "Small Chops"),
            ("Mosa",               "Traditional Nigerian mosa — contact us for pricing",           1, "Small Chops"),
        ]
        for name, desc, price, cat in ucc_meals:
            db.add(models.Meal(name=name, description=desc, price=price, category=cat, vendor_id=ucc.id))

        db.commit()
        print("✅ Seed data created — Chef'N (9 meals) + Ur Cravings Crunches (28 items)")


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