FROM python:3.12-slim

WORKDIR /app

# Abhängigkeiten installieren (inkl. python-multipart für Datei-Uploads)
COPY requirements.txt* ./
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic python-multipart

# Anwendungsdaten kopieren
COPY ./app /app/app

# Verzeichnisse für SQLite und Bilder vorbereiten
RUN mkdir -p /app/data/uploads /app/app/static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
