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

@app.post("/order")
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
    return crud.create_order(db, order)