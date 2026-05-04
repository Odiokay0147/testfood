from pydantic import BaseModel
from datetime import datetime

class OrderCreate(BaseModel):
    user_id: int
    meal_id: int
    quantity: int
    schedule_type: str
    delivery_date: datetime

class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str