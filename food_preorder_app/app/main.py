from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
import app.models as models
import app.schemas as schemas
import app.crud as crud

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# DB connection
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ✅ RUN ON STARTUP
@app.on_event("startup")
def startup_event():
    db = SessionLocal()

    # Create sample vendor + meal if not exists
    if not db.query(models.Vendor).first():
        vendor = models.Vendor(name="ChafN")
        db.add(vendor)
        db.commit()
        db.refresh(vendor)

        meal = models.Meal(
            name="Spaghetti + Chicken",
            price=5000,
            vendor_id=vendor.id
        )
        db.add(meal)
        db.commit()

    db.close()

@app.post("/order")
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    return crud.create_order(db, order)

# Optional home route
@app.get("/")
def home():
    return {"message": "Food Preorder API running 🚀"}