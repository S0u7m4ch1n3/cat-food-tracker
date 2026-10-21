import os
import sqlite3
import shutil
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Futter")

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

    # Tabelle: Einstellungen (Sprache, Setup-Status, Bewertungs-Begriffe)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Tabelle: Katzen
    c.execute("""
        CREATE TABLE IF NOT EXISTS cats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

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

    # Tabelle: Fütterungen (inkl. batch_id für Gruppierung)
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
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

    # Prüfen, ob batch_id in einer bestehenden Datenbank nachgerüstet werden muss
    cols = [row["name"] for row in c.execute("PRAGMA table_info(feedings)").fetchall()]
    if "batch_id" not in cols:
        c.execute("ALTER TABLE feedings ADD COLUMN batch_id TEXT")

    # Bestehende Einträge ohne batch_id automatisch nach (Zeitpunkt + Futter + Notiz) gruppieren
    null_batches = c.execute("SELECT COUNT(*) as cnt FROM feedings WHERE batch_id IS NULL OR batch_id = ''").fetchone()["cnt"]
    if null_batches > 0:
        groups = c.execute("""
            SELECT timestamp, manufacturer_name, food_name, IFNULL(notes, '') as n
            FROM feedings
            WHERE batch_id IS NULL OR batch_id = ''
            GROUP BY timestamp, manufacturer_name, food_name, IFNULL(notes, '')
        """).fetchall()
        for g in groups:
            b_id = str(uuid.uuid4())
            c.execute("""
                UPDATE feedings
                SET batch_id = ?
                WHERE (batch_id IS NULL OR batch_id = '')
                  AND timestamp = ?
                  AND manufacturer_name = ?
                  AND food_name = ?
                  AND IFNULL(notes, '') = ?
            """, (b_id, g["timestamp"], g["manufacturer_name"], g["food_name"], g["n"]))

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

    # Standard-Hersteller & Futter anlegen, falls leer
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

    # Standard-Settings initialisieren
    default_settings = {
        "language": "de",
        "rating_3": "Weggeatmet",
        "rating_2": "Okay",
        "rating_1": "Verweigert",
        "setup_completed": "0"
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Migration bestehender Katzen aus der Historie (damit bei Upgrade keine Daten fehlen)
    cat_cnt = c.execute("SELECT COUNT(*) as cnt FROM cats").fetchone()["cnt"]
    feed_cnt = c.execute("SELECT COUNT(*) as cnt FROM feedings").fetchone()["cnt"]
    vomit_cnt = c.execute("SELECT COUNT(*) as cnt FROM vomits").fetchone()["cnt"]

    if cat_cnt == 0 and (feed_cnt > 0 or vomit_cnt > 0):
        existing_cats = set()
        for r in c.execute("SELECT DISTINCT cat_name FROM feedings").fetchall():
            if r["cat_name"] and r["cat_name"] != "Unbekannt":
                existing_cats.add(r["cat_name"])
        for r in c.execute("SELECT DISTINCT cat_name FROM vomits").fetchall():
            if r["cat_name"] and r["cat_name"] != "Unbekannt":
                existing_cats.add(r["cat_name"])
        for cname in sorted(existing_cats):
            c.execute("INSERT OR IGNORE INTO cats (name) VALUES (?)", (cname,))
        if existing_cats:
            c.execute("UPDATE settings SET value = '1' WHERE key = 'setup_completed'")

    conn.commit()
    conn.close()


init_db()


# --- PYDANTIC MODELLE ---

class SettingsUpdate(BaseModel):
    language: Optional[str] = None
    rating_3: Optional[str] = None
    rating_2: Optional[str] = None
    rating_1: Optional[str] = None
    setup_completed: Optional[str] = None

class InitialSetupPayload(BaseModel):
    language: str
    cats: List[str]

class CatCreate(BaseModel):
    name: str

class CatUpdate(BaseModel):
    name: str

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

class FeedingBatchPayload(BaseModel):
    cat_ratings: Dict[str, int]
    manufacturer_id: int
    food_id: int
    notes: Optional[str] = ""
    timestamp: Optional[str] = None


# --- ROUTEN: SETTINGS & ERST-SETUP ---

@app.get("/api/settings")
def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


@app.put("/api/settings")
def update_settings(data: SettingsUpdate):
    conn = get_db()
    c = conn.cursor()
    updates = data.dict(exclude_unset=True)
    for k, v in updates.items():
        if v is not None:
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v).strip()))
    conn.commit()
    conn.close()
    return get_settings()


@app.post("/api/setup")
def complete_initial_setup(data: InitialSetupPayload):
    clean_cats = [x.strip() for x in data.cats if x.strip()]
    if not clean_cats:
        raise HTTPException(status_code=400, detail="Mindestens eine Katze angeben")

    conn = get_db()
    c = conn.cursor()
    lang = "en" if data.language == "en" else "de"
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('language', ?)", (lang,))

    # Falls Englisch beim Erststart gewählt wurde und noch die deutschen Standard-Begriffe drin stehen, anpassen
    if lang == "en":
        r3 = c.execute("SELECT value FROM settings WHERE key = 'rating_3'").fetchone()
        if r3 and r3["value"] == "Weggeatmet":
            c.execute("UPDATE settings SET value = 'Inhaled' WHERE key = 'rating_3'")
            c.execute("UPDATE settings SET value = 'Okay' WHERE key = 'rating_2'")
            c.execute("UPDATE settings SET value = 'Refused' WHERE key = 'rating_1'")

    for cname in clean_cats:
        c.execute("INSERT OR IGNORE INTO cats (name) VALUES (?)", (cname,))

    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('setup_completed', '1')")
    conn.commit()
    conn.close()
    return {"status": "ok"}


# --- ROUTEN: KATZEN ---

@app.get("/api/cats")
def get_cats():
    conn = get_db()
    rows = conn.execute("SELECT id, name FROM cats ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/cats")
def create_cat(data: CatCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO cats (name) VALUES (?)", (name,))
        conn.commit()
        new_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Katze existiert bereits")
    conn.close()
    return {"id": new_id, "name": name}


@app.put("/api/cats/{cat_id}")
def update_cat(cat_id: int, data: CatUpdate):
    new_name = data.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT name FROM cats WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Katze nicht gefunden")
    old_name = row["name"]

    try:
        c.execute("UPDATE cats SET name = ? WHERE id = ?", (new_name, cat_id))
        # Historie & Spuck-Einträge automatisch mit umbenennen
        c.execute("UPDATE feedings SET cat_name = ? WHERE cat_name = ?", (new_name, old_name))
        c.execute("UPDATE vomits SET cat_name = ? WHERE cat_name = ?", (new_name, old_name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Eine Katze mit diesem Namen existiert bereits")
    conn.close()
    return {"status": "ok", "id": cat_id, "name": new_name}


@app.delete("/api/cats/{cat_id}")
def delete_cat(cat_id: int):
    # Löscht nur die Katze aus der aktiven Auswahl; Historie bleibt erhalten!
    conn = get_db()
    conn.execute("DELETE FROM cats WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# --- ROUTEN: HERSTELLER & FUTTERSORTEN ---

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
        raise HTTPException(status_code=400, detail="Hersteller existiert bereits")
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
        raise HTTPException(status_code=400, detail="Diese Sorte existiert bereits")
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


# --- ROUTEN: FÜTTERUNGEN (GRUPPIERT NACH BATCH_ID) ---

@app.get("/api/feedings")
def get_feedings(limit: int = 1000):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feedings ORDER BY timestamp DESC, id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/feedings")
def create_feeding(data: FeedingBatchPayload):
    if not data.cat_ratings:
        raise HTTPException(status_code=400, detail="Mindestens eine Katze auswählen")

    conn = get_db()
    c = conn.cursor()

    man = c.execute("SELECT name FROM manufacturers WHERE id = ?", (data.manufacturer_id,)).fetchone()
    food = c.execute("SELECT name FROM foods WHERE id = ?", (data.food_id,)).fetchone()
    if not man or not food:
        conn.close()
        raise HTTPException(status_code=400, detail="Hersteller oder Futter ungültig")

    ts = data.timestamp if data.timestamp else datetime.now().strftime("%Y-%m-%dT%H:%M")
    batch_id = str(uuid.uuid4())

    created_ids = []
    for cat_name, rating in data.cat_ratings.items():
        c.execute("""
            INSERT INTO feedings (batch_id, cat_name, manufacturer_id, food_id, manufacturer_name, food_name, rating, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, cat_name, data.manufacturer_id, data.food_id, man["name"], food["name"], rating, data.notes, ts))
        created_ids.append(c.lastrowid)

    conn.commit()
    conn.close()
    return {"status": "ok", "batch_id": batch_id, "created": created_ids}


@app.put("/api/feedings/batch/{batch_id}")
def update_feeding_batch(batch_id: str, data: FeedingBatchPayload):
    if not data.cat_ratings:
        raise HTTPException(status_code=400, detail="Mindestens eine Katze auswählen")

    conn = get_db()
    c = conn.cursor()

    man = c.execute("SELECT name FROM manufacturers WHERE id = ?", (data.manufacturer_id,)).fetchone()
    food = c.execute("SELECT name FROM foods WHERE id = ?", (data.food_id,)).fetchone()
    if not man or not food:
        conn.close()
        raise HTTPException(status_code=400, detail="Hersteller oder Futter ungültig")

    ts = data.timestamp if data.timestamp else datetime.now().strftime("%Y-%m-%dT%H:%M")

    # Alte Einträge dieser Fütterungsgruppe ersetzen
    c.execute("DELETE FROM feedings WHERE batch_id = ?", (batch_id,))
    for cat_name, rating in data.cat_ratings.items():
        c.execute("""
            INSERT INTO feedings (batch_id, cat_name, manufacturer_id, food_id, manufacturer_name, food_name, rating, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, cat_name, data.manufacturer_id, data.food_id, man["name"], food["name"], rating, data.notes, ts))

    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.delete("/api/feedings/batch/{batch_id}")
def delete_feeding_batch(batch_id: str):
    conn = get_db()
    conn.execute("DELETE FROM feedings WHERE batch_id = ?", (batch_id,))
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

    if cat_name in ("Unbekannt", "Unknown"):
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
def get_vomits(limit: int = 200):
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
