from pydantic import BaseModel, EmailStr, validator
from datetime import datetime
from typing import Optional, List


# ─────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────
class UserCreate(BaseModel):
    name: str
    email: str
    phone: str          # required for WhatsApp reminders e.g. +233XXXXXXXXX
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    phone: str

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# VENDOR / MEAL
# ─────────────────────────────────────────────
class MealOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    category: str
    is_available: bool
    vendor_id: int

    class Config:
        from_attributes = True


class VendorOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    phone: Optional[str]
    is_active: bool
    meals: List[MealOut] = []

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ORDER ITEMS
# ─────────────────────────────────────────────
class OrderItemIn(BaseModel):
    meal_id: int
    quantity: int

    @validator("quantity")
    def qty_must_be_positive(cls, v):
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class OrderItemOut(BaseModel):
    id: int
    meal_id: int
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ORDER
# ─────────────────────────────────────────────
class OrderCreate(BaseModel):
    vendor_id: int
    schedule_type: str          # hourly | daily | weekly
    delivery_date: datetime
    delivery_time: Optional[str] = None   # "13:00"
    payment_type: str           # deposit | full
    items: List[OrderItemIn]
    notes: Optional[str] = None

    @validator("schedule_type")
    def validate_schedule(cls, v):
        if v not in ("hourly", "daily", "weekly"):
            raise ValueError("schedule_type must be hourly, daily, or weekly")
        return v

    @validator("payment_type")
    def validate_payment_type(cls, v):
        if v not in ("deposit", "full"):
            raise ValueError("payment_type must be deposit or full")
        return v

    @validator("items")
    def items_not_empty(cls, v):
        if not v:
            raise ValueError("Order must contain at least one item")
        return v


class OrderOut(BaseModel):
    id: int
    order_ref: str
    user_id: int
    vendor_id: int
    total_price: float
    deposit_amount: float
    balance_due: float
    payment_type: str
    deposit_paid: bool
    balance_paid: bool
    schedule_type: str
    delivery_date: datetime
    delivery_time: Optional[str]
    status: str
    notes: Optional[str]
    discount_applied: bool
    discount_amount: float
    reminder_sent: bool
    created_at: datetime
    items: List[OrderItemOut] = []

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# PAYMENT
# ─────────────────────────────────────────────
class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    payment_type: str       # deposit | balance | full
    method: str             # mobile_money | cash | card | bank_transfer
    reference: Optional[str] = None

    @validator("payment_type")
    def validate_ptype(cls, v):
        if v not in ("deposit", "balance", "full"):
            raise ValueError("payment_type must be deposit, balance, or full")
        return v

    @validator("method")
    def validate_method(cls, v):
        allowed = ("mobile_money", "cash", "card", "bank_transfer")
        if v not in allowed:
            raise ValueError(f"method must be one of {allowed}")
        return v


class PaymentOut(BaseModel):
    id: int
    order_id: int
    amount: float
    payment_type: str
    method: str
    reference: Optional[str]
    status: str
    paid_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# ORDER STATUS UPDATE
# ─────────────────────────────────────────────
class StatusUpdate(BaseModel):
    status: str

    @validator("status")
    def validate_status(cls, v):
        allowed = ("pending", "confirmed", "ordered", "dispatched", "delivered", "cancelled")
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v