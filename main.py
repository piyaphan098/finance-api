from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
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

# ─── DATABASE CONNECTION ───────────────────────────────────────────────────────
# ตั้งค่า DATABASE_URL ใน Render → Environment Variables
# รูปแบบ: postgresql://user:password@host:port/dbname

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    """สร้าง connection ใหม่ทุกครั้ง (safe สำหรับ serverless / Render free tier)"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """สร้าง table ถ้ายังไม่มี — รันตอน startup ครั้งเดียว"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id      SERIAL PRIMARY KEY,
                    icon    TEXT    NOT NULL DEFAULT '💰',
                    name    TEXT    NOT NULL,
                    cat     TEXT    NOT NULL,
                    date    TEXT    NOT NULL,
                    amt     FLOAT   NOT NULL,
                    type    TEXT    NOT NULL CHECK (type IN ('income','expense','invest')),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
        conn.commit()

# รัน init ตอน startup
try:
    init_db()
    print("✅ Database connected & table ready")
except Exception as e:
    print(f"⚠️  DB init failed: {e}")


# ─── MODELS ───────────────────────────────────────────────────────────────────

class Transaction(BaseModel):
    icon: str = "💰"
    name: str
    cat: str
    date: str
    amt: float
    type: str  # income | expense | invest

class TransactionUpdate(BaseModel):
    icon: Optional[str] = None
    name: Optional[str] = None
    cat: Optional[str] = None
    date: Optional[str] = None
    amt: Optional[float] = None
    type: Optional[str] = None


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "app": "ฉลาดใช้ Finance API", "db": "PostgreSQL"}


@app.get("/transactions")
def get_transactions():
    """ดึงรายการทั้งหมด เรียงล่าสุดก่อน"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM transactions ORDER BY created_at DESC, id DESC")
            rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/transaction", status_code=201)
def add_transaction(item: Transaction):
    """เพิ่มรายการใหม่"""
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
    return dict(new_row)


@app.put("/transaction/{tx_id}")
def update_transaction(tx_id: int, item: TransactionUpdate):
    """แก้ไขรายการ — อัปเดตเฉพาะ field ที่ส่งมา"""
    # สร้าง SET clause เฉพาะ field ที่ไม่ใช่ None
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
    return dict(updated)


@app.delete("/transaction/{tx_id}")
def delete_transaction(tx_id: int):
    """ลบรายการตาม id"""
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
    return {"message": "deleted", "id": deleted["id"], "name": deleted["name"]}


@app.delete("/transactions")
def clear_all_transactions():
    """ลบทุกรายการ (ใช้ระวัง!)"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM transactions")
            count = cur.rowcount
        conn.commit()
    return {"message": "cleared", "deleted_count": count}


@app.get("/health")
def health_check():
    """ใช้เช็คว่า DB เชื่อมต่อได้จริง"""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as total FROM transactions")
                result = cur.fetchone()
        return {"status": "ok", "total_records": result["total"]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB error: {str(e)}")
