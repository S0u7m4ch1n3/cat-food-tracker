# 🐾 Cat Food & Vomit Tracker

Ein selbstgehosteter, mobiler Web-Tracker (PWA) zur lückenlosen Dokumentation und Analyse der Fütterungen und Magen-Darm-Vorfälle von Katzen. Speziell entwickelt für den Einsatz auf dem Smartphone-Homescreen (wie eine native App) mit vollautomatischer 12-Stunden-Korrelation zur Früherkennung von Futtermittelunverträglichkeiten.

![PWA Ready](https://img.shields.io/badge/PWA-Ready-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-Frontend-38Bdf8?logo=tailwindcss&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Selfhosted-2496ED?logo=docker&logoColor=white)

---

## ✨ Features

- **🍖 Schnelle Fütterungserfassung:** Multi-Katzen-Auswahl (Simsa, BamBam, LaBim, Pebbles), Kaskaden-Dropdown für Hersteller und Sorten (mit dynamischer "Neu hinzufügen"-Funktion) sowie Akzeptanz-Bewertungen (*Weggeatmet*, *Okay*, *Verweigert*).
- **🤮 Spuck-Tracker mit 12h-Korrelation:** Dokumentation von Spuck-Ereignissen (inkl. Foto-Upload) und automatischer Rückwärtssuche in der Datenbank: *Welche Katze hat in den letzten 12 Stunden was gefressen?*
- **📊 Auswertung & Statistik:** Automatische Rankings der Lieblingssorten (mit Akzeptanz-Durchschnitt) und ein "Unverträglichkeits-Radar", das potenzielle Futter-Auslöser vor Spuck-Vorfällen aufdeckt.
- **📋 Komplette Historie & Stammdaten:** Mahlzeiten filtern, bearbeiten oder löschen sowie ein eigener Administrations-Reiter zum Umbenennen und Bereinigen von Herstellern und Futtersorten (inkl. automatischer Historien-Synchronisation).
- **📱 PWA (Progressive Web App):** Lässt sich nahtlos auf dem Smartphone-Homescreen installieren (Fullscreen ohne Browser-Adressleiste).
- **🔒 Lokale Datensouveränität:** Läuft komplett selbstgehostet in einem Docker-Container auf SQLite-Basis.

---

## 🚀 Installation & Setup (Docker)

1. **Repository klonen:**
   ```bash
   git clone [https://github.com/S0u7m4ch1n3/cat-food-tracker.git](https://github.com/S0u7m4ch1n3/cat-food-tracker.git)
   cd cat-tracker

2. Container bauen und starten:
   ```bash
   docker compose up -d --build

3. Aufrufen:
   Die App läuft standardmäßig auf Port 8000 (oder über deinen Reverse Proxy / Nginx Proxy Manager mit lokalem AdGuard/DNS-Rewrite).

##🔒 Datenschutz

Persönliche Daten, die lokale SQLite-Datenbank und hochgeladene Spuck-Fotos verbleiben ausschließlich auf deinem Heimserver und sind über die .gitignore vom öffentlichen Upload ausgeschlossen.
