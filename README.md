# NetStock — Inventory & Asset Management

A full-stack web application for managing hardware assets, stock levels, budget allocations, purchase orders, and team tasks. Built with Flask + MongoDB Atlas. Deployed on Render via gunicorn.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 / Flask 3.0.3 |
| Database | MongoDB Atlas — MongoEngine 0.29.3 ORM |
| Auth | Flask-Login 0.6.3 + Flask-Bcrypt 1.0.1 |
| Forms / CSRF | Flask-WTF 1.2.1 |
| Real-time | Flask-SocketIO 5.3.6 (threading async mode) |
| Rate limiting | Flask-Limiter 3.9.0 |
| Caching | Flask-Caching 2.3.0 (SimpleCache, in-process) |
| Web Push | pywebpush ≥1.14 (VAPID) |
| Excel | openpyxl 3.1.5 |
| WSGI | gunicorn 23.0.0 (gthread workers) |
| Frontend | Bootstrap 5 + Bootstrap Icons (CDN), vanilla JS, Socket.IO client |
| PWA | Web App Manifest + Service Worker |

---

## Prerequisites

- Python 3.11
- A [MongoDB Atlas](https://www.mongodb.com/atlas) cluster (free tier works)
- (Optional) SMTP credentials for email
- (Optional) VAPID key pair for Web Push notifications (`pywebpush` CLI can generate them)

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/a0556776530-boop/netsctock.git
cd netsctock

# 2. Create virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set MONGO_URI and SECRET_KEY at minimum

# 5. Run dev server
python run.py
```

Open **http://127.0.0.1:5000**

### First-run admin account

On first launch the app seeds a default super-admin. Check `app/seed.py` for credentials or create one via the MongoDB shell:

```python
# In a Python shell with venv active:
from app import create_app
app = create_app()
with app.app_context():
    from app.models.user import User
    from flask_bcrypt import Bcrypt
    bcrypt = Bcrypt(app)
    User(name='Admin', password_hash=bcrypt.generate_password_hash('changeme').decode(), role='super_admin').save()
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `MONGO_URI` | **Yes** | MongoDB Atlas connection string: `mongodb+srv://user:pass@cluster.mongodb.net/netstock?appName=Cluster0` |
| `SECRET_KEY` | **Yes** | Flask session secret — use `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SMTP_HOST` | No | SMTP server (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (e.g. `587`) |
| `SMTP_EMAIL` | No | Sender email address |
| `SMTP_PASSWORD` | No | SMTP app password |
| `VAPID_PRIVATE_KEY` | No | VAPID private key for Web Push (newlines escaped as `\n`) |
| `VAPID_PUBLIC_KEY` | No | VAPID public key |
| `VAPID_EMAIL` | No | VAPID contact (default: `mailto:admin@netstock.app`) |
| `ALLOWED_ORIGIN` | No | Comma-separated CORS origins for SocketIO (default: `*`) |
| `FLASK_DEBUG` | No | Set to `1` in development to disable secure-only cookies |

---

## Project Structure

```
netstock/
├── wsgi.py                  # Production WSGI entry point
├── run.py                   # Dev entry point
├── Procfile                 # Render / Heroku deploy command
├── requirements.txt
├── runtime.txt              # python-3.11.0
├── .env.example
│
└── app/
    ├── __init__.py          # App factory: create_app()
    ├── config.py            # Config class — reads env vars
    ├── seed.py              # CLI seed commands
    │
    ├── models/
    │   ├── user.py          # User (roles: super_admin, admin, viewer, warehouse)
    │   ├── asset.py         # Asset, AssetType, AssetEvent
    │   ├── site.py          # Site (physical locations)
    │   ├── task.py          # Task
    │   ├── estimate.py      # Estimate / Allocation + EstimateItem (embedded)
    │   ├── purchase.py      # Purchase + PurchaseItem (embedded)
    │   ├── pool.py          # Budget Pool + PoolTransaction (embedded)
    │   ├── activity.py      # ActivityLog (TTL 60 days)
    │   ├── login_event.py   # LoginEvent (TTL 90 days)
    │   ├── page_visit.py    # PageVisit (TTL 90 days)
    │   ├── settings.py      # AppSetting (key-value config store)
    │   ├── chat_message.py
    │   ├── chat_group.py
    │   ├── chat_file.py     # Binary files stored as base64 in MongoDB
    │   ├── chat_last_read.py
    │   └── chat_typing.py   # TTL 5 seconds
    │
    ├── routes/
    │   ├── auth.py          # /auth — login, logout, change-password
    │   ├── main.py          # / — dashboard + API endpoints
    │   ├── assets.py        # /assets
    │   ├── tasks.py         # /tasks
    │   ├── admin.py         # /admin — user management, settings
    │   ├── estimates.py     # /estimates — allocations & budget estimates
    │   ├── purchases.py     # /purchases
    │   ├── pools.py         # /pools — budget pools (EMF funds)
    │   ├── chat.py          # /chat — REST API for chat
    │   └── chat_socket.py   # SocketIO event handlers
    │
    ├── utils/
    │   ├── activity.py      # log_activity() helper
    │   ├── cache.py         # Flask-Caching instance (import from here)
    │   ├── events.py        # log_event() for AssetEvent
    │   ├── exchange.py      # USD → ILS rate helper (cached)
    │   ├── login_recorder.py
    │   ├── mongo_helpers.py # get_or_404()
    │   └── translations.py  # EN / HE translation dict
    │
    ├── static/
    │   ├── manifest.json    # PWA manifest
    │   ├── css/style.css
    │   ├── js/app.js
    │   └── js/chat.js
    │
    └── templates/
        ├── base.html        # Main app shell (authenticated pages)
        ├── base_public.html # Login page shell (aurora background)
        ├── _macros.html     # Jinja2 macros: avatar()
        ├── dashboard.html
        ├── auth/
        ├── admin/
        ├── assets/
        ├── tasks/
        ├── estimates/
        ├── purchases/
        ├── pools/
        └── chat/
```

---

## User Roles

| Role | Permissions |
|---|---|
| `super_admin` | Full access — user management, role changes, settings, all data |
| `admin` | All data operations, create/delete users (not super_admin), login history |
| `viewer` | Read-only access to all data |
| `warehouse` | Redirected to estimates; can mark allocations received/completed |

---

## Key Business Logic

### Price calculation
`Final NIS price = USD price × usd_base_rate × bina_factor × maintenance_factor × vat_factor`

Default factors (overridable in Admin → Settings):
- `usd_base_rate`: 3.6
- `bina_factor`: 1.048
- `maintenance_factor`: 1.7
- `vat_factor`: 1.18

### Allocation counter
Sequential allocation numbers are stored in `AppSetting` under key `alloc_counter`. Incremented atomically per allocation created.

### Stock level calculation
`Available = quantity + in_purchase_qty - committed_qty`

Where `committed_qty` = sum of all `EstimateItem.quantity` for pending allocations, and `in_purchase_qty` = sum of active `PurchaseItem.quantity`.

### Session invalidation
Each `User` has a `session_version` integer. On password change it increments. Flask-Login's `user_loader` checks the stored version against the session cookie — stale sessions are rejected within ~20 seconds (heartbeat cycle).

---

## Caching

`Flask-Caching SimpleCache` — in-process memory, **not shared across gunicorn workers**.

Key cache keys and TTLs:
| Key | TTL | Contents |
|---|---|---|
| `_user_photos` | 90s | `{user_name: base64_photo}` dict for avatar rendering |
| `user_activity_api` | 10s | User presence data for dashboard |
| `unread_{user_id}` | 25s | Chat unread count per user |
| `_dashboard_data` (memoized) | 60s | All heavy aggregation results |
| `_activity_feed` (memoized) | 30s | Last 30 activity log entries |
| `_expiring_estimates` (memoized) | 45s | Allocations expiring within 7 days |

> **Production note**: With 2 gunicorn workers, each has its own cache. For true cache sharing, replace `SimpleCache` with `RedisCache`.

---

## Real-time (SocketIO)

Flask-SocketIO runs in `threading` async mode (required for gunicorn gthread workers). Each authenticated user joins:
- A personal notification room: `user_{user_id}`
- A room per chat group they belong to: `grp_{group_id}`

Chat events: `chat_join`, `chat_send`, `chat_typing`, `chat_seen` → server emits `chat_message`, `chat_confirmed`, `chat_notify`, `chat_read`, `chat_typing`.

---

## File Storage

**No cloud storage.** All files are stored in MongoDB:
- **Profile photos**: `User.profile_photo` — base64 JPEG data URI (256×256)
- **Asset photos**: `Asset.photo` — base64 data URI
- **Chat files**: `ChatFile.data` — base64 data URI (up to ~50 MB enforced by `MAX_CONTENT_LENGTH`)
- **BOM documents**: `app/uploads/bom/` — local filesystem on the server

> On Render's ephemeral filesystem, BOM file uploads are lost on redeploy. Move to S3/R2 if persistence is needed.

---

## Deployment (Render)

The `Procfile` runs:
```
web: gunicorn --worker-class=gthread --workers=2 --threads=8 --timeout=60 --max-requests=1000 --max-requests-jitter=100 wsgi:app
```

Required environment variables on Render:
- `MONGO_URI`
- `SECRET_KEY`
- (Optional) VAPID keys, SMTP

MongoDB Atlas: whitelist `0.0.0.0/0` in Network Access (Render IPs are dynamic).

---

## i18n (Hebrew / English)

Language is stored in `session['lang']` (default: `he`). Switch via `/set-lang/en` or `/set-lang/he`.

All UI strings are in `app/utils/translations.py` as a nested dict: `TRANSLATIONS['he']` and `TRANSLATIONS['en']`. Injected into templates via `before_request` as `g.t`.

---

## Avatar System

`app/templates/_macros.html` exports the `avatar(name, photos, size=28)` macro.

- `photos` — `dict` passed explicitly from each route (`{user_name: base64_photo}`)
- `avatar_color(name)` — Jinja2 global set at startup, returns a deterministic color from a palette based on `hash(name)`
- Falls back to a colored circle with initials when no photo exists

Routes that pass `user_photos`: `main.dashboard`, `tasks.list_tasks`, `tasks.history`, `admin.users`.
