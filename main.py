from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Literal
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="ฉลาดใช้ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── DATABASE ─────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("❌ DATABASE_URL is not set")

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    icon TEXT NOT NULL DEFAULT '💰',
                    name TEXT NOT NULL,
                    cat TEXT NOT NULL,
                    date TEXT NOT NULL,
                    amt FLOAT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('income','expense','invest')),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # 🔥 เพิ่ม index (performance + ดูโปร)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_type ON transactions(type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON transactions(date);")

        conn.commit()

try:
    init_db()
    print("✅ Database ready")
except Exception as e:
    print(f"⚠️ DB init failed: {e}")

# ─── MODELS ─────────────────────────────────────────────────────

class Transaction(BaseModel):
    icon: str = "💰"
    name: str
    cat: str
    date: str
    amt: float
    type: Literal["income", "expense", "invest"]  # 🔥 strict validation

class TransactionUpdate(BaseModel):
    icon: Optional[str] = None
    name: Optional[str] = None
    cat: Optional[str] = None
    date: Optional[str] = None
    amt: Optional[float] = None
    type: Optional[Literal["income", "expense", "invest"]] = None

# ─── ROUTES ─────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "ok",
        "app": "ฉลาดใช้ Finance API",
        "db": "PostgreSQL"
    }

@app.get("/transactions")
def get_transactions():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM transactions ORDER BY created_at DESC, id DESC")
            rows = cur.fetchall()
    return rows

@app.post("/transaction", status_code=201)
def add_transaction(item: Transaction):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (icon, name, cat, date, amt, type)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (item.icon, item.name, item.cat, item.date, item.amt, item.type)
            )
            new_row = cur.fetchone()
        conn.commit()
    return new_row

@app.put("/transaction/{tx_id}")
def update_transaction(tx_id: int, item: TransactionUpdate):
    fields = {k: v for k, v in item.dict().items() if v is not None}

    if not fields:
        raise HTTPException(status_code=400, detail="ไม่มีข้อมูลที่จะอัปเดต")

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [tx_id]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE transactions SET {set_clause} WHERE id = %s RETURNING *",
                values
            )
            updated = cur.fetchone()
        conn.commit()

    if not updated:
        raise HTTPException(status_code=404, detail=f"ไม่พบรายการ id={tx_id}")

    return updated

@app.delete("/transaction/{tx_id}")
def delete_transaction(tx_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM transactions WHERE id = %s RETURNING id, name",
                (tx_id,)
            )
            deleted = cur.fetchone()
        conn.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail=f"ไม่พบรายการ id={tx_id}")

    return {
        "message": "deleted",
        "id": deleted["id"],
        "name": deleted["name"]
    }

@app.delete("/transactions")
def clear_all_transactions():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM transactions")
            count = cur.rowcount
        conn.commit()
    return {"message": "cleared", "deleted_count": count}

@app.get("/health")
def health_check():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as total FROM transactions")
                result = cur.fetchone()
        return {"status": "ok", "total_records": result["total"]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB error: {str(e)}")
