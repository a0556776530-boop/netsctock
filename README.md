# Inventory — Network Hardware Asset Tracker

A Flask web app for tracking Cisco/network hardware inventory, pricing, and stock levels.
Runs as a local web server (dev) or as a standalone Windows EXE (production).

---

## Quick Start (Development)

### Prerequisites
- Python 3.11 or later  
- pip

### 1. Clone the repository
```bash
git clone https://github.com/a0556776530/netstock.git
cd netstock
```

### 2. Create and activate a virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```
Edit `.env` and set a strong `SECRET_KEY`.  
Everything else works with defaults for local development.

### 5. Run the development server
```bash
python run.py
```

Open **http://127.0.0.1:5000** in your browser.

### Default credentials (first run only)
| Field    | Value               |
|----------|---------------------|
| Email    | admin@inventory.app |
| Password | admin1234           |

> Change the password immediately after first login.

---

## Database

The database (`inventory.db`) is **not committed** to the repository — it is created
automatically on first run with a default admin user and reference data.

To reset to a clean slate, delete `inventory.db` and restart the server.

---

## Project Structure

```
netstock/
├── app/
│   ├── models/          # SQLAlchemy models (Asset, User, Site, Task, AppSetting)
│   ├── routes/          # Flask blueprints (assets, auth, admin, sites, tasks, main)
│   ├── static/          # CSS, JS
│   ├── templates/       # Jinja2 HTML templates
│   └── utils/           # Translations, exchange rate, email helpers
├── migrations/          # Flask-Migrate / Alembic migration scripts
├── .env.example         # Environment variable template — copy to .env
├── netstock.spec        # PyInstaller build spec
├── netstock_launcher.py # EXE entry point (auto-migration, browser open)
├── requirements.txt     # Python dependencies
└── run.py               # Development server entry point
```

---

## Global Price Settings

On the Assets page a **Global Price Settings** bar lets you configure:

| Setting       | Default | Description                              |
|---------------|---------|------------------------------------------|
| USD Rate (₪)  | 3.00    | How many NIS per 1 USD                   |
| Conv. Fee (%) | 0       | Broker / conversion fee percentage       |
| Bynet Factor  | 1.048   | Bynet markup multiplier                  |

Settings are saved to the database and persist across restarts.  
**Formula:** `USD × rate × bynet × (1 + fee%) × 1.18 VAT`

---

## Building the Windows EXE

Requires PyInstaller (`pip install pyinstaller`):

```bash
pyinstaller --clean --noconfirm netstock.spec
```

Output: `dist/Inventory.exe` — single-file executable, no Python required on the target machine.

---

## Environment Variables

| Variable        | Required | Default                  | Description              |
|-----------------|----------|--------------------------|--------------------------|
| `SECRET_KEY`    | **Yes**  | dev placeholder          | Flask session secret     |
| `DATABASE_URL`  | No       | `sqlite:///inventory.db` | SQLAlchemy DB URL        |
| `MAIL_SERVER`   | No       | `smtp.gmail.com`         | SMTP for email reminders |
| `MAIL_PORT`     | No       | `587`                    | SMTP port                |
| `MAIL_USERNAME` | No       | —                        | SMTP login               |
| `MAIL_PASSWORD` | No       | —                        | SMTP password            |

---

## User Roles

| Role          | Permissions                             |
|---------------|-----------------------------------------|
| `admin`       | Full access — users, export, all assets |
| `technician`  | View + edit assets and tasks            |
| `viewer`      | Read-only                               |
