import os
import io
import csv
import html
import sqlite3
import shutil
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Futter")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = "/app/data"
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
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
            vomit_type TEXT DEFAULT 'food',
            timestamp TEXT NOT NULL,
            notes TEXT,
            image_path TEXT
        )
    """)

    # Prüfen, ob vomit_type in einer bestehenden Datenbank nachgerüstet werden muss
    v_cols = [row["name"] for row in c.execute("PRAGMA table_info(vomits)").fetchall()]
    if "vomit_type" not in v_cols:
        c.execute("ALTER TABLE vomits ADD COLUMN vomit_type TEXT DEFAULT 'food'")
        c.execute("UPDATE vomits SET vomit_type = 'food' WHERE vomit_type IS NULL OR vomit_type = ''")

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
        if not item.get("vomit_type"):
            item["vomit_type"] = "food"
        item["recent_feedings"] = get_recent_feedings_for_vomit(conn, item["cat_name"], item["timestamp"])
        result.append(item)
    conn.close()
    return result


@app.post("/api/vomits")
async def create_vomit(
    cat_name: str = Form(...),
    vomit_type: Optional[str] = Form("food"),
    timestamp: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    image: Optional[UploadFile] = File(None)
):
    ts = timestamp if timestamp else datetime.now().strftime("%Y-%m-%dT%H:%M")
    v_type = vomit_type if vomit_type in ("food", "bile_grass", "hairball", "other") else "food"
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
        INSERT INTO vomits (cat_name, vomit_type, timestamp, notes, image_path)
        VALUES (?, ?, ?, ?, ?)
    """, (cat_name, v_type, ts, notes, img_rel_path))
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


# --- ROUTEN: EXPORT (CSV & PDF-BERICHT) ---

def _vomit_type_label(vtype: str, lang: str = "de") -> str:
    labels = {
        "de": {
            "food": "Unverdautes Futter",
            "bile_grass": "Galle / Schaum / Gras",
            "hairball": "Haarballen",
            "other": "Sonstiges / Unklar"
        },
        "en": {
            "food": "Undigested Food",
            "bile_grass": "Bile / Foam / Grass",
            "hairball": "Hairball",
            "other": "Other / Unclear"
        }
    }
    l_dict = labels["en"] if lang == "en" else labels["de"]
    return l_dict.get(vtype or "food", l_dict["food"])


@app.get("/api/export/csv")
def export_csv():
    conn = get_db()
    settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
    s_map = {r["key"]: r["value"] for r in settings_rows}
    lang = s_map.get("language", "de")
    r_labels = {
        3: s_map.get("rating_3", "Weggeatmet"),
        2: s_map.get("rating_2", "Okay"),
        1: s_map.get("rating_1", "Verweigert")
    }

    feedings_rows = conn.execute("SELECT * FROM feedings ORDER BY timestamp DESC, id DESC").fetchall()
    vomits_rows = conn.execute("SELECT * FROM vomits ORDER BY timestamp DESC").fetchall()
    conn.close()

    # Vorbereiten der futterrelevanten Spuck-Ereignisse (12h-Fenster)
    food_vomits = []
    for v in vomits_rows:
        vtype = v["vomit_type"] if "vomit_type" in v.keys() and v["vomit_type"] else "food"
        if vtype in ("food", "other"):
            try:
                v_dt = datetime.fromisoformat(v["timestamp"])
                food_vomits.append((v["cat_name"], v_dt, vtype, v["timestamp"]))
            except ValueError:
                pass

    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM für direkte Lesbarkeit in Excel
    writer = csv.writer(output, delimiter=";")

    if lang == "en":
        writer.writerow([
            "Date", "Time", "Batch_ID", "Brand", "Variety",
            "Cat", "Rating_Score", "Rating_Label", "Notes", "Food_Vomit_Within_12h"
        ])
    else:
        writer.writerow([
            "Datum", "Uhrzeit", "Batch_ID", "Hersteller", "Futtersorte",
            "Katze", "Bewertung_Score", "Bewertung_Text", "Notiz", "Futter_Erbrochen_12h"
        ])

    for f in feedings_rows:
        ts_str = f["timestamp"] or ""
        date_part = ts_str[:10] if len(ts_str) >= 10 else ts_str
        time_part = ts_str[11:16] if len(ts_str) >= 16 else ""

        vomit_hit = "Nein" if lang != "en" else "No"
        try:
            f_dt = datetime.fromisoformat(ts_str)
            for v_cat, v_dt, v_type, v_ts in food_vomits:
                if v_cat in (f["cat_name"], "Unbekannt", "Unknown"):
                    diff_hours = (v_dt - f_dt).total_seconds() / 3600.0
                    if 0 <= diff_hours <= 12:
                        vomit_hit = f"{'Ja' if lang != 'en' else 'Yes'} ({v_ts[11:16]} - {_vomit_type_label(v_type, lang)})"
                        break
        except ValueError:
            pass

        writer.writerow([
            date_part,
            time_part,
            f["batch_id"] or "",
            f["manufacturer_name"],
            f["food_name"],
            f["cat_name"],
            f["rating"],
            r_labels.get(f["rating"], str(f["rating"])),
            f["notes"] or "",
            vomit_hit
        ])

    filename = f"futter_export_{datetime.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/export/pdf", response_class=HTMLResponse)
def export_pdf_report(hide_deleted: bool = False):
    conn = get_db()
    s_map = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
    lang = s_map.get("language", "de")
    r_labels = {
        3: s_map.get("rating_3", "Weggeatmet"),
        2: s_map.get("rating_2", "Okay"),
        1: s_map.get("rating_1", "Verweigert")
    }

    active_cats = [r["name"] for r in conn.execute("SELECT name FROM cats ORDER BY id ASC").fetchall()]
    active_set = set(active_cats)

    all_feedings = [dict(r) for r in conn.execute("SELECT * FROM feedings ORDER BY timestamp DESC, id DESC").fetchall()]
    all_vomits = [dict(r) for r in conn.execute("SELECT * FROM vomits ORDER BY timestamp DESC").fetchall()]
    conn.close()

    if hide_deleted:
        all_feedings = [f for f in all_feedings if f["cat_name"] in active_set]
        all_vomits = [v for v in all_vomits if v["cat_name"] in active_set or v["cat_name"] in ("Unbekannt", "Unknown")]

    cat_columns = list(active_cats)
    if not hide_deleted:
        for f in all_feedings:
            if f["cat_name"] and f["cat_name"] not in cat_columns:
                cat_columns.append(f["cat_name"])

    # Futterrelevante Spuck-Ereignisse ermitteln (für Unverträglichkeits-Markierung)
    food_vomit_events = []
    vomit_type_counts = {"food": 0, "bile_grass": 0, "hairball": 0, "other": 0}
    for v in all_vomits:
        vtype = v.get("vomit_type") or "food"
        vomit_type_counts[vtype] = vomit_type_counts.get(vtype, 0) + 1
        if vtype in ("food", "other"):
            try:
                food_vomit_events.append((v["cat_name"], datetime.fromisoformat(v["timestamp"]), v))
            except ValueError:
                pass

    # --- TEIL 1: GESAMT-AUSWERTUNG ÜBER DEN GESAMTEN ZEITRAUM ---
    food_summary = {}
    for f in all_feedings:
        key = f"{f['manufacturer_name']} – {f['food_name']}"
        if key not in food_summary:
            food_summary[key] = {
                "label": key,
                "count": 0,
                "sum_rating": 0,
                "cat_scores": {},
                "vomit_hits": 0,
                "vomit_cats": set()
            }
        entry = food_summary[key]
        entry["count"] += 1
        entry["sum_rating"] += f["rating"]
        c_name = f["cat_name"]
        if c_name not in entry["cat_scores"]:
            entry["cat_scores"][c_name] = []
        entry["cat_scores"][c_name].append(f["rating"])

        # Prüfen ob binnen 12h nach dieser Mahlzeit Futter-Erbrechen auftrat
        try:
            f_dt = datetime.fromisoformat(f["timestamp"])
            for v_cat, v_dt, _ in food_vomit_events:
                if v_cat in (c_name, "Unbekannt", "Unknown"):
                    diff_h = (v_dt - f_dt).total_seconds() / 3600.0
                    if 0 <= diff_h <= 12:
                        entry["vomit_hits"] += 1
                        entry["vomit_cats"].add(c_name)
                        break
        except ValueError:
            pass

    sorted_foods = sorted(
        food_summary.values(),
        key=lambda x: (x["sum_rating"] / x["count"] if x["count"] else 0, x["count"]),
        reverse=True
    )

    # --- TEIL 2: LETZTE 30 TAGE FILTERN ---
    cutoff_dt = datetime.now() - timedelta(days=30)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M")

    recent_vomits = [v for v in all_vomits if (v.get("timestamp") or "") >= cutoff_str]
    recent_feedings = [f for f in all_feedings if (f.get("timestamp") or "") >= cutoff_str]

    # Gruppieren der letzten 30 Tage Fütterungen nach batch_id
    grouped_30d = []
    batch_map = {}
    for f in recent_feedings:
        b_key = f.get("batch_id") or f"single_{f['id']}"
        if b_key not in batch_map:
            grp = {
                "timestamp": f["timestamp"],
                "food_label": f"{f['manufacturer_name']} – {f['food_name']}",
                "notes": f.get("notes") or "",
                "items": []
            }
            batch_map[b_key] = grp
            grouped_30d.append(grp)
        batch_map[b_key]["items"].append((f["cat_name"], f["rating"]))

    def fmt_dt(iso_s: str) -> str:
        try:
            d = datetime.fromisoformat(iso_s)
            return d.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return iso_s or ""

    # HTML-Tabellenzeilen für Gesamt-Matrix bauen
    cat_headers_html = "".join(f"<th>🐱 {html.escape(c)}</th>" for c in cat_columns)
    matrix_rows_html = ""
    for item in sorted_foods:
        avg_val = item["sum_rating"] / item["count"] if item["count"] else 0
        badge_cls = "good" if avg_val >= 2.5 else ("ok" if avg_val >= 1.8 else "bad")
        cat_cells = ""
        for c in cat_columns:
            scores = item["cat_scores"].get(c, [])
            if not scores:
                cat_cells += "<td class='muted'>–</td>"
            else:
                c_avg = sum(scores) / len(scores)
                c_cls = "good" if c_avg >= 2.5 else ("ok" if c_avg >= 1.8 else "bad")
                warn = " ⚠️" if c in item["vomit_cats"] else ""
                cat_cells += f"<td><span class='pill {c_cls}'>Ø {c_avg:.1f} ({len(scores)}x){warn}</span></td>"

        vomit_cell = (
            f"<span class='pill bad'>⚠️ {item['vomit_hits']}x</span>"
            if item["vomit_hits"] > 0
            else "<span class='muted'>0x</span>"
        )
        matrix_rows_html += f"""
            <tr>
                <td><strong>{html.escape(item['label'])}</strong></td>
                <td>{item['count']}</td>
                <td><span class='pill {badge_cls}'>Ø {avg_val:.2f} / 3.00</span></td>
                {cat_cells}
                <td>{vomit_cell}</td>
            </tr>
        """

    if not matrix_rows_html:
        matrix_rows_html = f"<tr><td colspan='{4 + len(cat_columns)}' class='muted'>Keine Fütterungsdaten vorhanden.</td></tr>"

    # HTML-Tabellenzeilen für Spuck-Ereignisse (letzte 30 Tage)
    vomit_30d_rows = ""
    for v in recent_vomits:
        vtype = v.get("vomit_type") or "food"
        is_rel = vtype in ("food", "other")
        rel_badge = (
            f"<span class='pill bad'>🚨 {html.escape(_vomit_type_label(vtype, lang))}</span>"
            if is_rel
            else f"<span class='pill neutral'>ℹ️ {html.escape(_vomit_type_label(vtype, lang))}</span>"
        )
        vomit_30d_rows += f"""
            <tr>
                <td>{fmt_dt(v.get('timestamp', ''))}</td>
                <td><strong>{html.escape(v.get('cat_name', ''))}</strong></td>
                <td>{rel_badge}</td>
                <td>{html.escape(v.get('notes') or '–')}</td>
            </tr>
        """
    if not vomit_30d_rows:
        vomit_30d_rows = "<tr><td colspan='4' class='muted'>Keine Spuck-Ereignisse in den letzten 30 Tagen.</td></tr>"

    # HTML-Tabellenzeilen für Fütterungen (letzte 30 Tage)
    feed_30d_rows = ""
    for g in grouped_30d:
        ratings_str = ", ".join(
            f"<strong>{html.escape(c)}:</strong> {html.escape(r_labels.get(r, str(r)))} ({r})"
            for c, r in g["items"]
        )
        feed_30d_rows += f"""
            <tr>
                <td style="white-space:nowrap;">{fmt_dt(g['timestamp'])}</td>
                <td><strong>{html.escape(g['food_label'])}</strong></td>
                <td>{ratings_str}</td>
                <td>{html.escape(g['notes'] or '–')}</td>
            </tr>
        """
    if not feed_30d_rows:
        feed_30d_rows = "<tr><td colspan='4' class='muted'>Keine Fütterungen in den letzten 30 Tagen.</td></tr>"

    total_meals_all = len(all_feedings)
    overall_avg = f"{(sum(f['rating'] for f in all_feedings) / total_meals_all):.2f}" if total_meals_all else "–"
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <title>Futter – Auswertungs- & Tierarztbericht ({now_str})</title>
    <style>
        @page {{ size: A4 portrait; margin: 14mm; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #0f172a;
            background: #ffffff;
            margin: 0;
            padding: 20px;
            font-size: 12px;
            line-height: 1.45;
        }}
        .no-print {{
            background: #0f172a;
            color: #f8fafc;
            padding: 12px 18px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .btn {{
            background: #2563eb;
            color: #fff;
            border: none;
            padding: 8px 14px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            font-size: 12px;
        }}
        h1 {{ font-size: 20px; margin: 0 0 4px 0; }}
        h2 {{
            font-size: 14px;
            margin: 22px 0 8px 0;
            padding-bottom: 4px;
            border-bottom: 2px solid #e2e8f0;
            color: #1e293b;
        }}
        .meta {{ color: #64748b; font-size: 11px; margin-bottom: 14px; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 18px;
        }}
        .kpi {{
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 10px;
            background: #f8fafc;
        }}
        .kpi .label {{ font-size: 10px; text-transform: uppercase; color: #64748b; }}
        .kpi .val {{ font-size: 16px; font-weight: 700; margin-top: 2px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
            font-size: 11px;
        }}
        th, td {{
            border: 1px solid #cbd5e1;
            padding: 6px 8px;
            text-align: left;
            vertical-align: top;
        }}
        th {{ background: #f1f5f9; font-weight: 600; }}
        .muted {{ color: #94a3b8; font-style: italic; }}
        .pill {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 5px;
            font-weight: 600;
            font-size: 10px;
        }}
        .pill.good {{ background: #dcfce7; color: #166534; }}
        .pill.ok {{ background: #dbeafe; color: #1e40af; }}
        .pill.bad {{ background: #ffe4e6; color: #9f1239; }}
        .pill.neutral {{ background: #f1f5f9; color: #475569; }}
        @media print {{
            body {{ padding: 0; }}
            .no-print {{ display: none !important; }}
        }}
    </style>
</head>
<body>
    <div class="no-print">
        <div>
            <strong>🐾 Futter – Druck- & PDF-Ansicht</strong>
            <span style="margin-left:10px; color:#94a3b8;">Wähle im Druckdialog „Als PDF speichern“.</span>
        </div>
        <div style="display:flex; gap:8px;">
            <button class="btn" onclick="window.print()">🖨️ Als PDF speichern / Drucken</button>
            <button class="btn" style="background:#475569;" onclick="window.close()">Schließen</button>
        </div>
    </div>

    <h1>🐾 Futter – Gesamt-Auswertung & 30-Tage-Bericht</h1>
    <div class="meta">
        Erstellt am: {now_str} Uhr | Aktive Katzen: {", ".join(active_cats) if active_cats else "–"} |
        Bewertungs-Skala: 3 = {html.escape(r_labels[3])}, 2 = {html.escape(r_labels[2])}, 1 = {html.escape(r_labels[1])}
    </div>

    <div class="kpi-grid">
        <div class="kpi">
            <div class="label">Gesamte Katzen-Mahlzeiten</div>
            <div class="val">{total_meals_all}</div>
        </div>
        <div class="kpi">
            <div class="label">Ø Akzeptanz (Gesamt)</div>
            <div class="val">{overall_avg} / 3.00</div>
        </div>
        <div class="kpi">
            <div class="label">Spuck-Vorfälle (Gesamt)</div>
            <div class="val">{len(all_vomits)} (davon {vomit_type_counts.get('food', 0)}x Futter)</div>
        </div>
        <div class="kpi">
            <div class="label">Einträge letzte 30 Tage</div>
            <div class="val">{len(grouped_30d)} Runden / {len(recent_vomits)}x Spucken</div>
        </div>
    </div>

    <h2>1. Generelle Futter-Auswertung & Akzeptanz-Matrix (Gesamter Zeitraum)</h2>
    <p class="meta">
        Zeigt für jede Futtersorte die durchschnittliche Bewertung pro Katze über den gesamten Zeitraum.
        <strong>⚠️ Futter-Spucken (12h)</strong> zählt ausschließlich futterrelevante Spuck-Ereignisse (ohne Haarballen oder Galle/Gras).
    </p>
    <table>
        <thead>
            <tr>
                <th>Hersteller & Futtersorte</th>
                <th>Portionen</th>
                <th>Ø Gesamt</th>
                {cat_headers_html}
                <th>Futter-Spucken (12h)</th>
            </tr>
        </thead>
        <tbody>
            {matrix_rows_html}
        </tbody>
    </table>

    <h2>2. Spuck-Ereignisse der letzten 30 Tage</h2>
    <table>
        <thead>
            <tr>
                <th style="width:130px;">Zeitpunkt</th>
                <th style="width:120px;">Katze</th>
                <th style="width:190px;">Art / Kategorie</th>
                <th>Notiz / Details</th>
            </tr>
        </thead>
        <tbody>
            {vomit_30d_rows}
        </tbody>
    </table>

    <h2>3. Chronologische Fütterungen der letzten 30 Tage (Gruppiert nach Mahlzeit)</h2>
    <table>
        <thead>
            <tr>
                <th style="width:130px;">Zeitpunkt</th>
                <th style="width:220px;">Hersteller & Sorte</th>
                <th>Katzen & Einzelbewertung</th>
                <th style="width:160px;">Notiz</th>
            </tr>
        </thead>
        <tbody>
            {feed_30d_rows}
        </tbody>
    </table>

    <script>
        window.addEventListener('load', () => {{
            setTimeout(() => window.print(), 350);
        }});
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_doc)


# --- STATISCHE DATEIEN & FRONTEND ---

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
