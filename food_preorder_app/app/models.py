from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    password = Column(String)

    orders = relationship("Order", back_populates="user")


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    meals = relationship("Meal", back_populates="vendor")
    orders = relationship("Order", back_populates="vendor")


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String, nullable=True)
    price = Column(Float)
    category = Column(String, default="Main")
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    is_available = Column(Boolean, default=True)

    vendor = relationship("Vendor", back_populates="meals")
    order_items = relationship("OrderItem", back_populates="meal")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_ref = Column(String, unique=True, index=True)       # e.g. PG-2506011200-AB3C
    user_id = Column(Integer, ForeignKey("users.id"))
    vendor_id = Column(Integer, ForeignKey("vendors.id"))

    total_price = Column(Float)
    deposit_amount = Column(Float)                             # amount due at booking
    balance_due = Column(Float)                                # remaining before dispatch
    payment_type = Column(String, default="deposit")          # "deposit" | "full"

    deposit_paid = Column(Boolean, default=False)
    balance_paid = Column(Boolean, default=False)

    schedule_type = Column(String)                             # hourly | daily | weekly
    delivery_date = Column(DateTime)
    delivery_time = Column(String, nullable=True)              # e.g. "13:00"
    status = Column(String, default="pending")  # pending|confirmed|ordered|dispatched|delivered|cancelled
    notes = Column(String, nullable=True)
    discount_applied = Column(Boolean, default=False)
    discount_amount = Column(Float, default=0.0)
    reminder_sent = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    vendor = relationship("Vendor", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """One row per meal line — supports multi-item orders."""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    meal_id = Column(Integer, ForeignKey("meals.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Float)       # price snapshot at order time
    subtotal = Column(Float)

    order = relationship("Order", back_populates="items")
    meal = relationship("Meal", back_populates="order_items")


class Payment(Base):
    """Records every payment transaction against an order."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    amount = Column(Float)
    payment_type = Column(String)        # deposit | balance | full
    method = Column(String, default="mobile_money")  # mobile_money|cash|card|bank_transfer
    reference = Column(String, nullable=True)         # external transaction ref
    status = Column(String, default="completed")      # pending|completed|failed
    paid_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="payments")


class Reminder(Base):
    """Log of every reminder message sent to customers."""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    reminder_type = Column(String)   # balance_reminder | dispatch_reminder
    message = Column(String)
    sent_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", back_populates="reminders")