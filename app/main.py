import os
import sqlite3
import shutil
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Cat Food & Vomit Tracker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = "/app/data"
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Tabelle: Hersteller
    c.execute("""
        CREATE TABLE IF NOT EXISTS manufacturers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    # Tabelle: Futtersorten
    c.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manufacturer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (manufacturer_id) REFERENCES manufacturers (id) ON DELETE CASCADE,
            UNIQUE(manufacturer_id, name)
        )
    """)

    # Tabelle: Fütterungen
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_name TEXT NOT NULL,
            manufacturer_id INTEGER,
            food_id INTEGER,
            manufacturer_name TEXT NOT NULL,
            food_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            notes TEXT,
            timestamp TEXT NOT NULL
        )
    """)

    # Tabelle: Spuck-Ereignisse
    c.execute("""
        CREATE TABLE IF NOT EXISTS vomits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            notes TEXT,
            image_path TEXT
        )
    """)

    # Standard-Einträge anlegen, falls Datenbank noch komplett leer ist
    c.execute("SELECT COUNT(*) as cnt FROM manufacturers")
    if c.fetchone()["cnt"] == 0:
        default_data = {
            "MAC's": ["Rind & Hühnerherzen", "Ente, Pute & Huhn", "Lachs & Huhn"],
            "Mjamjam": ["Saftiges Huhn an Möhrchen", "Känguru pur", "Insekt & Huhn"],
            "Catz Finefood": ["Geflügel", "Wild & Rotbarsch", "Lamm & Kaninchen"],
            "Animonda Carny": ["Rind pur", "Rind + Huhn", "Multifleisch-Cocktail"]
        }
        for man_name, food_list in default_data.items():
            c.execute("INSERT INTO manufacturers (name) VALUES (?)", (man_name,))
            man_id = c.lastrowid
            for f_name in food_list:
                c.execute("INSERT INTO foods (manufacturer_id, name) VALUES (?, ?)", (man_id, f_name))

    conn.commit()
    conn.close()


init_db()


# --- PYDANTIC MODELLE ---

class ManufacturerCreate(BaseModel):
    name: str

class ManufacturerUpdate(BaseModel):
    name: str

class FoodCreate(BaseModel):
    manufacturer_id: int
    name: str

class FoodUpdate(BaseModel):
    manufacturer_id: int
    name: str

class FeedingCreate(BaseModel):
    cats: List[str]
    manufacturer_id: int
    food_id: int
    rating: int
    notes: Optional[str] = ""
    timestamp: Optional[str] = None

class FeedingUpdate(BaseModel):
    cat_name: str
    manufacturer_id: int
    food_id: int
    rating: int
    notes: Optional[str] = ""
    timestamp: str


# --- ROUTEN: STAMMDATEN (HERSTELLER & FUTTER) ---

@app.get("/api/manufacturers")
def get_manufacturers():
    conn = get_db()
    rows = conn.execute("SELECT id, name FROM manufacturers ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/manufacturers")
def create_manufacturer(data: ManufacturerCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO manufacturers (name) VALUES (?)", (name,))
        conn.commit()
        new_id = c.lastrowid
    except sqlite3.IntegrityError:
        row = c.execute("SELECT id FROM manufacturers WHERE name = ?", (name,)).fetchone()
        new_id = row["id"] if row else None
    finally:
        conn.close()
    return {"id": new_id, "name": name}


@app.put("/api/manufacturers/{man_id}")
def update_manufacturer(man_id: int, data: ManufacturerUpdate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT name FROM manufacturers WHERE id = ?", (man_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Hersteller nicht gefunden")
    old_name = row["name"]

    try:
        c.execute("UPDATE manufacturers SET name = ? WHERE id = ?", (name, man_id))
        c.execute("UPDATE feedings SET manufacturer_name = ? WHERE manufacturer_id = ? OR manufacturer_name = ?", (name, man_id, old_name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Ein Hersteller mit diesem Namen existiert bereits")
    conn.close()
    return {"status": "ok", "id": man_id, "name": name}


@app.delete("/api/manufacturers/{man_id}")
def delete_manufacturer(man_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM foods WHERE manufacturer_id = ?", (man_id,))
    c.execute("DELETE FROM manufacturers WHERE id = ?", (man_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/api/foods")
def get_foods():
    conn = get_db()
    rows = conn.execute("SELECT id, manufacturer_id, name FROM foods ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/foods")
def create_food(data: FoodCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO foods (manufacturer_id, name) VALUES (?, ?)", (data.manufacturer_id, name))
        conn.commit()
        new_id = c.lastrowid
    except sqlite3.IntegrityError:
        row = c.execute("SELECT id FROM foods WHERE manufacturer_id = ? AND name = ?", (data.manufacturer_id, name)).fetchone()
        new_id = row["id"] if row else None
    finally:
        conn.close()
    return {"id": new_id, "manufacturer_id": data.manufacturer_id, "name": name}


@app.put("/api/foods/{food_id}")
def update_food(food_id: int, data: FoodUpdate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT name FROM foods WHERE id = ?", (food_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Futtersorte nicht gefunden")
    old_name = row["name"]

    try:
        c.execute("UPDATE foods SET name = ?, manufacturer_id = ? WHERE id = ?", (name, data.manufacturer_id, food_id))
        c.execute("UPDATE feedings SET food_name = ?, manufacturer_id = ? WHERE food_id = ? OR food_name = ?", (name, data.manufacturer_id, food_id, old_name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Diese Sorte existiert bei diesem Hersteller bereits")
    conn.close()
    return {"status": "ok", "id": food_id, "name": name}


@app.delete("/api/foods/{food_id}")
def delete_food(food_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM foods WHERE id = ?", (food_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# --- ROUTEN: FÜTTERUNGEN ---

@app.get("/api/feedings")
def get_feedings(cat: Optional[str] = None, limit: int = 200):
    conn = get_db()
    if cat and cat != "Alle":
        rows = conn.execute(
            "SELECT * FROM feedings WHERE cat_name = ? ORDER BY timestamp DESC LIMIT ?",
            (cat, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM feedings ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/feedings")
def create_feeding(data: FeedingCreate):
    if not data.cats:
        raise HTTPException(status_code=400, detail="Mindestens eine Katze auswählen")

    conn = get_db()
    c = conn.cursor()

    man = c.execute("SELECT name FROM manufacturers WHERE id = ?", (data.manufacturer_id,)).fetchone()
    food = c.execute("SELECT name FROM foods WHERE id = ?", (data.food_id,)).fetchone()
    if not man or not food:
        conn.close()
        raise HTTPException(status_code=400, detail="Hersteller oder Futter ungültig")

    ts = data.timestamp if data.timestamp else datetime.now().strftime("%Y-%m-%dT%H:%M")

    created_ids = []
    for cat in data.cats:
        c.execute("""
            INSERT INTO feedings (cat_name, manufacturer_id, food_id, manufacturer_name, food_name, rating, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (cat, data.manufacturer_id, data.food_id, man["name"], food["name"], data.rating, data.notes, ts))
        created_ids.append(c.lastrowid)

    conn.commit()
    conn.close()
    return {"status": "ok", "created": created_ids}


@app.put("/api/feedings/{feeding_id}")
def update_feeding(feeding_id: int, data: FeedingUpdate):
    conn = get_db()
    c = conn.cursor()

    man = c.execute("SELECT name FROM manufacturers WHERE id = ?", (data.manufacturer_id,)).fetchone()
    food = c.execute("SELECT name FROM foods WHERE id = ?", (data.food_id,)).fetchone()
    if not man or not food:
        conn.close()
        raise HTTPException(status_code=400, detail="Hersteller oder Futter ungültig")

    c.execute("""
        UPDATE feedings
        SET cat_name = ?, manufacturer_id = ?, food_id = ?, manufacturer_name = ?, food_name = ?, rating = ?, notes = ?, timestamp = ?
        WHERE id = ?
    """, (data.cat_name, data.manufacturer_id, data.food_id, man["name"], food["name"], data.rating, data.notes, data.timestamp, feeding_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.delete("/api/feedings/{feeding_id}")
def delete_feeding(feeding_id: int):
    conn = get_db()
    conn.execute("DELETE FROM feedings WHERE id = ?", (feeding_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# --- ROUTEN: SPUCK-TRACKER & 12h-KORRELATION ---

def get_recent_feedings_for_vomit(conn, cat_name: str, vomit_ts_str: str):
    try:
        vomit_dt = datetime.fromisoformat(vomit_ts_str)
    except ValueError:
        return []
    start_dt = vomit_dt - timedelta(hours=12)
    start_str = start_dt.strftime("%Y-%m-%dT%H:%M")
    end_str = vomit_dt.strftime("%Y-%m-%dT%H:%M")

    if cat_name == "Unbekannt":
        rows = conn.execute("""
            SELECT cat_name, manufacturer_name, food_name, timestamp
            FROM feedings
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp DESC
        """, (start_str, end_str)).fetchall()
    else:
        rows = conn.execute("""
            SELECT cat_name, manufacturer_name, food_name, timestamp
            FROM feedings
            WHERE cat_name = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp DESC
        """, (cat_name, start_str, end_str)).fetchall()

    return [dict(r) for r in rows]


@app.get("/api/vomits")
def get_vomits(limit: int = 100):
    conn = get_db()
    rows = conn.execute("SELECT * FROM vomits ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["recent_feedings"] = get_recent_feedings_for_vomit(conn, item["cat_name"], item["timestamp"])
        result.append(item)
    conn.close()
    return result


@app.post("/api/vomits")
async def create_vomit(
    cat_name: str = Form(...),
    timestamp: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    image: Optional[UploadFile] = File(None)
):
    ts = timestamp if timestamp else datetime.now().strftime("%Y-%m-%dT%H:%M")
    img_rel_path = None

    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower() or ".jpg"
        safe_name = f"vomit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
        full_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(full_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        img_rel_path = f"/uploads/{safe_name}"

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO vomits (cat_name, timestamp, notes, image_path)
        VALUES (?, ?, ?, ?)
    """, (cat_name, ts, notes, img_rel_path))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"status": "ok", "id": new_id}


@app.delete("/api/vomits/{vomit_id}")
def delete_vomit(vomit_id: int):
    conn = get_db()
    row = conn.execute("SELECT image_path FROM vomits WHERE id = ?", (vomit_id,)).fetchone()
    if row and row["image_path"]:
        filename = os.path.basename(row["image_path"])
        file_on_disk = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_on_disk):
            try:
                os.remove(file_on_disk)
            except OSError:
                pass
    conn.execute("DELETE FROM vomits WHERE id = ?", (vomit_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# --- STATISCHE DATEIEN & FRONTEND ---

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
