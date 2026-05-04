from sqlalchemy.orm import Session
import app.models as models
from app.auth import hash_password

def create_order(db: Session, order):
    meal = db.query(models.Meal).filter(models.Meal.id == order.meal_id).first()

    total_price = meal.price * order.quantity
    deposit = total_price * 0.3
    balance = total_price - deposit

    db_order = models.Order(
        user_id=order.user_id,
        meal_id=order.meal_id,
        quantity=order.quantity,
        total_price=total_price,
        deposit_paid=deposit,
        balance=balance,
        schedule_type=order.schedule_type,
        delivery_date=order.delivery_date
    )

    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    return db_order

def create_user(db, user):
    hashed_pw = hash_password(user.password)

    db_user = models.User(
        name=user.name,
        email=user.email,
        password=hashed_pw
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


def authenticate_user(db, email, password):
    user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        return None

    from app.auth import verify_password
    if not verify_password(password, user.password):
        return None

    return user