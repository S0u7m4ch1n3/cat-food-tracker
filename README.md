# 🐾 Cat Food & Vomit Tracker

Ein selbstgehosteter, mobiler Web-Tracker (PWA) zur lückenlosen Dokumentation und Analyse von Fütterungen und Spuck-Ereignissen bei Katzen.

![PWA Ready](https://img.shields.io/badge/PWA-Ready-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-Frontend-38BDF8?logo=tailwindcss&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Selfhosted-2496ED?logo=docker&logoColor=white)

---

## ✨ Features

- **🥣 Schnelle Fütterungserfassung:** Multi-Katzen-Auswahl für eine schnelle Erfassung von Mahlzeiten.
- **🤮 Spuck-Tracker mit 12h-Korrelation:** Dokumentation von Spuck-Ereignissen (inkl. Foto-Upload) mit automatischer Zuordnung zu den Mahlzeiten der letzten 12 Stunden.
- **📊 Auswertung & Statistik:** Automatische Rankings der Lieblingssorten (mit Akzeptanz-Quote) und Auswertung der Verträglichkeit.
- **📋 Komplette Historie & Stammdaten:** Mahlzeiten filtern, bearbeiten oder löschen sowie Katzen und Futtersorten verwalten.
- **📱 PWA (Progressive Web App):** Lässt sich nahtlos auf dem Smartphone-Homescreen installieren und fühlt sich wie eine native App an.
- **🔒 Lokale Datensouveränität:** Läuft komplett selbstgehostet in einem Docker-Container, ganz ohne Cloud.

---

## 🚀 Installation & Setup (Docker)

1. **Repository klonen:**

   ```bash
   git clone https://github.com/S0u7m4ch1n3/cat-food-tracker.git
   cd cat-tracker
   ```

2. **Container bauen und starten:**

   ```bash
   docker compose up -d --build
   ```

3. **Funktions- / Health-Check:**

   Prüfe, ob der Container reibungslos läuft und gestartet ist:

   ```bash
   docker ps
   docker logs cat-food-tracker
   ```

4. **Aufrufen:**

   Die App läuft standardmäßig auf Port `8000` (oder über deinen Reverse Proxy / Nginx Proxy Manager mit lokalem AdGuard/DNS-Rewrite).

---

## 🔒 Datenschutz

Persönliche Daten, die lokale SQLite-Datenbank und hochgeladenen Spuck-Fotos verbleiben ausschließlich auf deinem Heimserver und sind über die `.gitignore` vom öffentlichen Upload ausgeschlossen.

---

## Deploy

docker-compose.yml

```bash
services:
  cat-food-tracker:
    image: ghcr.io/s0u7m4ch1n3/cat-food-tracker:latest
    container_name: cat-food-tracker
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
```