# 🐾 Cat Food & Vomit Tracker

A self-hosted, mobile-first web tracker (PWA) for seamless documentation and analysis of feedings and vomiting incidents in cats.

![PWA Ready](https://img.shields.io/badge/PWA-Ready-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-Frontend-38BDF8?logo=tailwindcss&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Selfhosted-2496ED?logo=docker&logoColor=white)

<!-- TODO: add screenshots once the design is finalized
![Screenshot](docs/screenshot.png)
-->

---

## 📖 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Build from Source](#-build-from-source)
- [First Run](#-first-run)
- [Installing as an App (PWA)](#-installing-as-an-app-pwa)
- [Usage](#-usage)
- [Exports & Reports](#-exports--reports)
- [Configuration](#-configuration)
- [Data & Backup](#-data--backup)
- [Updating](#-updating)
- [Security Notice](#-security-notice)
- [Privacy](#-privacy)
- [API](#-api)
- [Local Development](#-local-development)
- [Project Structure](#-project-structure)
- [Contributing](#-contributing)
- [License](#-license)
- [Disclaimer](#-disclaimer)

---

## ✨ Features

- **🥣 Quick Feeding Logging:** Select one or more cats per meal and rate each cat individually on a three-level acceptance scale. Add optional notes and adjust date and time if needed.
- **🤮 Vomit Tracker with 12h Correlation:** Document vomiting incidents with an optional photo, a category and notes. For food-relevant incidents, the app looks up which meals the cat was fed in the **previous 12 hours** and flags the connection. Over time, this helps to detect and document food intolerances.
- **📊 Analysis & Statistics:** Rankings of favorite food varieties (with acceptance rate) and evaluation of how well each food is tolerated.
- **📋 Complete History & Master Data:** Filter, edit or delete meals, and manage cats, manufacturers and food varieties. New entries can also be created on the fly in the selection form.
- **🌍 Bilingual:** German and English interface, selectable on first start and in the settings.
- **🏷️ Custom Rating Labels:** Rename the three acceptance levels to whatever suits you (defaults: *Inhaled / Okay / Refused*).
- **📤 Export:** Full CSV export plus a printable report (save it as PDF) with an all-time food matrix per cat and the last 30 days of vomiting incidents and meals.
- **🕒 Automatic Timestamps:** Date and time are recorded for every entry.
- **📱 PWA (Progressive Web App):** Installs seamlessly on your smartphone's home screen and feels like a native app.
- **🔒 Local Data Sovereignty:** Runs entirely self-hosted in a single Docker container, with no cloud involved.

### Vomit categories

| Category               | Counts as food-relevant? |
|------------------------|:------------------------:|
| Undigested food        | ✅                       |
| Other / unclear        | ✅                       |
| Bile / foam / grass    | ❌                       |
| Hairball               | ❌                       |

Only food-relevant incidents are used for the intolerance analysis in the exports.

---

## 🧰 Tech Stack

| Layer     | Technology                              |
|-----------|-----------------------------------------|
| Backend   | Python 3.12, FastAPI, Uvicorn           |
| Database  | SQLite                                  |
| Frontend  | Tailwind CSS (PWA)                      |
| Packaging | Docker, GitHub Actions (prebuilt image) |

---

## 🚀 Quick Start

The easiest way to run the tracker is the prebuilt image from the GitHub Container Registry.

1. **Create a `docker-compose.yml`:**

   ```yaml
   services:
     cat-food-tracker:
       image: ghcr.io/s0u7m4ch1n3/cat-food-tracker:latest
       container_name: cat-food-tracker
       restart: unless-stopped
       ports:
         - "8000:8000"
       environment:
         - TZ=Europe/Berlin   # set your own time zone
       volumes:
         - ./data:/app/data
   ```

2. **Start the container:**

   ```bash
   docker compose up -d
   ```

3. **Health check:**

   Verify that the container started and is running smoothly:

   ```bash
   docker ps
   docker logs cat-food-tracker
   ```

4. **Open the app:**

   By default, the app is available at `http://<your-server-ip>:8000` (or behind your reverse proxy / Nginx Proxy Manager with a local AdGuard/DNS rewrite).

---

## 🔨 Build from Source

If you prefer to build the image yourself:

```bash
git clone https://github.com/S0u7m4ch1n3/cat-food-tracker.git
cd cat-food-tracker
docker compose up -d --build
```

---

## 👋 First Run

On the first start, a short setup asks for:

1. your preferred **language** (German or English), and
2. the **names of your cats** (at least one).

The app also comes with a few example manufacturers and food varieties, which you can edit or delete in the master data at any time.

---

## 📱 Installing as an App (PWA)

Open the tracker in your phone's browser, then:

- **iOS (Safari):** Tap the *Share* button → *Add to Home Screen*.
- **Android (Chrome):** Open the menu (⋮) → *Install app* / *Add to Home screen*.

> **Note:** Most mobile browsers require **HTTPS** for installing PWAs and for camera access. If you access the app via a plain `http://` address in your local network, these features may not be available. Use a reverse proxy with a valid certificate to enable them.

---

## 🐱 Usage

### Logging a feeding

1. Select one or more cats.
2. Select the manufacturer and food. New ones can be created directly in the selection form or in the master data.
3. Rate how well the food was accepted by each cat (three levels, editable in the settings).
4. Optionally add a note and adjust date/time, then save.

Cats fed in the same round are stored as one meal, so they can be edited or deleted together.

### Logging a vomiting incident

1. Select the cat (or *Unknown* if you did not see who it was).
2. Choose the category (see [Vomit categories](#vomit-categories)).
3. Optionally take or upload a photo and add a note.
4. Save. For food-relevant incidents, the meals of the previous 12 hours are looked up and shown with the entry. For *Unknown*, the meals of all cats are considered.

### Master data

Manage cats, manufacturers and food varieties under *Master Data*:

- Renaming a cat, manufacturer or food also updates the existing history.
- Deleting a cat only removes it from the active selection; its history is kept.
- Deleting a manufacturer also removes its food varieties from the selection; past meals keep their recorded names.

---

## 📤 Exports & Reports

- **CSV:** Complete export of all feedings. Semicolon-separated with a UTF-8 BOM, so it opens directly in Excel. Each row contains date, time, batch ID, manufacturer, food, cat, rating (score and label), notes and a flag showing whether a food-relevant vomiting incident followed within 12 hours.
- **PDF report:** Opens a print-optimized page and starts the print dialog; choose *Save as PDF*. It contains:
  1. an all-time food matrix with the average acceptance per cat and the number of food-related vomiting incidents within 12 hours of a meal,
  2. all vomiting incidents of the last 30 days,
  3. all meals of the last 30 days, grouped by feeding round.

  Handy for veterinary visits. Add `?hide_deleted=true` to the report URL to exclude cats that have been removed from the active selection.

---

## ⚙️ Configuration

Most settings are made in the app itself:

| Setting          | Where            | Default                          |
|------------------|------------------|----------------------------------|
| Language         | Settings         | `de` (chosen on first start)     |
| Rating labels    | Settings         | Inhaled / Okay / Refused         |

Container options:

| Option           | How                                   | Default      |
|------------------|---------------------------------------|--------------|
| Port             | `ports` in `docker-compose.yml`       | `8000`       |
| Time zone        | `TZ` environment variable             | container time (UTC) |
| Data directory   | volume mounted to `/app/data`         | `./data`     |

> **Tip:** Set `TZ` so that automatically generated timestamps match your local time.

---

## 💾 Data & Backup

All persistent data lives in the mounted `./data` directory:

| Path                | Content                |
|---------------------|------------------------|
| `data/tracker.db`   | SQLite database        |
| `data/uploads/`     | Uploaded vomit photos  |

**Backup:** Stop the container (recommended for a consistent database state) and copy the whole `data` folder:

```bash
docker compose stop
cp -r ./data ./data-backup-$(date +%F)
docker compose start
```

**Restore:** Put the backed-up `data` folder back in place and restart the container.

Database changes between versions are applied automatically on startup.

---

## 🔄 Updating

```bash
docker compose pull
docker compose up -d
```

Your data in `./data` is preserved.

---

## ⚠️ Security Notice

The tracker currently has **no login or password protection**. Anyone who can reach the app can view and modify all data and open uploaded photos. Do **not** expose it directly to the internet. Run it only in your home network, or put it behind a reverse proxy with authentication (e.g. basic auth, Authelia) or a VPN.

---

## 🔒 Privacy

Personal data, the local SQLite database and uploaded vomit photos stay exclusively on your home server and are excluded from public upload via `.gitignore`.

---

## 🔌 API

The app is built on a REST API. Interactive documentation (Swagger UI) is available at `http://localhost:8000/docs`.

| Area           | Endpoints                                                      |
|----------------|----------------------------------------------------------------|
| Settings/Setup | `GET/PUT /api/settings`, `POST /api/setup`                     |
| Cats           | `GET/POST /api/cats`, `PUT/DELETE /api/cats/{id}`              |
| Manufacturers  | `GET/POST /api/manufacturers`, `PUT/DELETE /api/manufacturers/{id}` |
| Foods          | `GET/POST /api/foods`, `PUT/DELETE /api/foods/{id}`            |
| Feedings       | `GET/POST /api/feedings`, `PUT/DELETE /api/feedings/batch/{batch_id}` |
| Vomits         | `GET/POST /api/vomits`, `DELETE /api/vomits/{id}`              |
| Export         | `GET /api/export/csv`, `GET /api/export/pdf`                   |

---

## 🛠️ Local Development

Running without Docker works with a recent Python version (3.12 recommended). The app stores its data in the directory given by the `DATA_DIR` environment variable (default: `/app/data`).

```bash
git clone https://github.com/S0u7m4ch1n3/cat-food-tracker.git
cd cat-food-tracker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATA_DIR="$PWD/data"
uvicorn app.main:app --reload --port 8000
```

Then open `http://localhost:8000`.

---

## 🗂️ Project Structure

```text
cat-food-tracker/
├── app/
│   ├── main.py          # FastAPI app: API, database setup, exports
│   └── static/          # Frontend (index.html, PWA assets)
├── data/                # Created at runtime
│   ├── tracker.db       # SQLite database
│   └── uploads/         # Uploaded photos
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🤝 Contributing

Contributions are always welcome! Feel free to:

- open an [issue](https://github.com/S0u7m4ch1n3/cat-food-tracker/issues) for bugs or feature ideas,
- fork the repository and submit a pull request.

There is no fixed roadmap; new features are added as they come up.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🩺 Disclaimer

This tool is meant for documentation purposes only and does **not** replace veterinary advice. If your cat vomits frequently or shows other signs of illness, please consult a veterinarian.
