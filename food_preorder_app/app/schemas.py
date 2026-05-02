from pydantic import BaseModel
from datetime import datetime

class OrderCreate(BaseModel):
    user_id: int
    meal_id: int
    quantity: int
    schedule_type: str
    delivery_date: datetime