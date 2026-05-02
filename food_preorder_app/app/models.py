from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True)
    password = Column(String)


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    name = Column(String)


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Float)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    meal_id = Column(Integer, ForeignKey("meals.id"))
    quantity = Column(Integer)

    total_price = Column(Float)
    deposit_paid = Column(Float)
    balance = Column(Float)

    schedule_type = Column(String)  # hourly/daily/weekly
    delivery_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")