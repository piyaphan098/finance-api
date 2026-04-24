from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json, os

app = FastAPI(title="ฉลาดใช้ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory store (ถ้าต้องการ persistent ให้เปลี่ยนเป็น DB ทีหลัง)
DATA_FILE = "transactions.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class Transaction(BaseModel):
    icon: str = "💰"
    name: str
    cat: str
    date: str
    amt: float
    type: str  # income | expense | invest

@app.get("/")
def root():
    return {"status": "ok", "app": "ฉลาดใช้ Finance API"}

@app.get("/transactions")
def get_transactions():
    return load_data()

@app.post("/transaction")
def add_transaction(item: Transaction):
    data = load_data()
    data.insert(0, item.dict())  # เพิ่มไว้ด้านบน (ล่าสุดก่อน)
    save_data(data)
    return {"message": "added", "total": len(data)}

@app.delete("/transactions")
def clear_transactions():
    save_data([])
    return {"message": "cleared"}
