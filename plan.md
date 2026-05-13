# Netstock — Hardware Asset Tracking System
## Master Plan

---

## 1. Project Overview

A browser-based web application for tracking technical hardware assets (SFP modules, switches, and similar network equipment) through their full lifecycle — from dismantling at a site (e.g., Beit VaGan) to storage, assignment, and redeployment. The system supports barcode/serial-number scanning directly in the browser.

---

## 2. Core Features

### 2.1 Asset Management
- Register hardware assets with serial number, type, model, manufacturer, and condition
- Track asset status: `In Use`, `Dismantled`, `In Storage`, `Assigned`, `Faulty`, `Retired`
- Assign assets to sites, racks, or personnel
- Attach notes and photos to asset records

### 2.2 Asset Flow (Lifecycle Tracking)
- Log every state transition with timestamp, location, and responsible user
- Track origin site (e.g., "Beit VaGan") and destination
- Full audit trail / history per asset
- Bulk dismantling workflow: scan multiple items at once from a site

### 2.3 Due Date Management
- Set due dates on assignments and tasks (e.g., return date, scheduled reinstall)
- Dashboard view filterable and sortable by Due Date
- Visual indicators for overdue, due soon, and on-time items
- Email/notification alerts for approaching due dates

### 2.4 Browser-Based Scanning
- Use device camera (via browser) to scan:
  - Barcodes (Code 128, Code 39, EAN, UPC)
  - QR codes
  - Manual serial number entry fallback
- Scanning available on asset registration, check-in, and check-out screens
- Works on desktop (webcam) and mobile (rear camera)

### 2.5 Reporting & Dashboard
- Summary dashboard: total assets, assets by status, overdue items
- Site-level inventory report
- Asset history export (CSV)
- Filter by: site, asset type, status, due date range

---

## 3. Tech Stack

| Layer        | Technology                              |
|------------- |-----------------------------------------|
| Backend      | Python 3.11+, Flask                     |
| Database     | SQLite (dev) → PostgreSQL (prod)        |
| ORM          | SQLAlchemy + Flask-Migrate (Alembic)    |
| Auth         | Flask-Login + Flask-Bcrypt              |
| Frontend     | Jinja2 templates, Bootstrap 5, vanilla JS |
| Scanning     | QuaggaJS (barcode) + html5-qrcode (QR) |
| Forms        | Flask-WTF + WTForms                     |
| Notifications| Flask-Mail (SMTP)                       |

---

## 4. Database Schema

### `users`
| Column       | Type        | Notes                  |
|--------------|-------------|------------------------|
| id           | INTEGER PK  |                        |
| name         | VARCHAR     |                        |
| email        | VARCHAR     | unique, login          |
| password_hash| VARCHAR     |                        |
| role         | ENUM        | admin, technician, viewer |
| created_at   | DATETIME    |                        |

### `sites`
| Column       | Type        | Notes                  |
|--------------|-------------|------------------------|
| id           | INTEGER PK  |                        |
| name         | VARCHAR     | e.g., "Beit VaGan"     |
| address      | TEXT        |                        |
| notes        | TEXT        |                        |

### `asset_types`
| Column       | Type        | Notes                  |
|--------------|-------------|------------------------|
| id           | INTEGER PK  |                        |
| name         | VARCHAR     | e.g., "SFP Module", "Switch" |
| category     | VARCHAR     | e.g., "Networking"     |

### `assets`
| Column        | Type        | Notes                              |
|---------------|-------------|-------------------------------------|
| id            | INTEGER PK  |                                     |
| serial_number | VARCHAR     | unique, scannable                   |
| barcode       | VARCHAR     | optional secondary identifier       |
| asset_type_id | FK          | → asset_types                       |
| model         | VARCHAR     |                                     |
| manufacturer  | VARCHAR     |                                     |
| status        | ENUM        | in_use, dismantled, in_storage, assigned, faulty, retired |
| current_site_id | FK        | → sites (current physical location) |
| assigned_to_id  | FK        | → users (nullable)                  |
| due_date      | DATE        | nullable, for assignment return     |
| notes         | TEXT        |                                     |
| created_at    | DATETIME    |                                     |
| updated_at    | DATETIME    |                                     |

### `asset_events`
| Column        | Type        | Notes                              |
|---------------|-------------|-------------------------------------|
| id            | INTEGER PK  |                                     |
| asset_id      | FK          | → assets                            |
| event_type    | ENUM        | dismantled, moved, assigned, returned, repaired, retired |
| from_site_id  | FK          | → sites (nullable)                  |
| to_site_id    | FK          | → sites (nullable)                  |
| performed_by  | FK          | → users                             |
| notes         | TEXT        |                                     |
| event_date    | DATETIME    |                                     |

### `tasks`
| Column        | Type        | Notes                              |
|---------------|-------------|-------------------------------------|
| id            | INTEGER PK  |                                     |
| title         | VARCHAR     |                                     |
| asset_id      | FK          | → assets (nullable)                 |
| assigned_to   | FK          | → users (nullable)                  |
| due_date      | DATE        |                                     |
| status        | ENUM        | pending, in_progress, done          |
| notes         | TEXT        |                                     |
| created_at    | DATETIME    |                                     |

---

## 5. Application Routes

### Auth
- `GET/POST /login` — login page
- `GET /logout` — logout

### Dashboard
- `GET /` — summary dashboard with due date alerts and asset status cards

### Assets
- `GET /assets` — asset list (filterable, sortable by due date)
- `GET /assets/new` — new asset form (with scanner)
- `POST /assets` — create asset
- `GET /assets/<id>` — asset detail + event history
- `GET /assets/<id>/edit` — edit form
- `POST /assets/<id>/edit` — update
- `POST /assets/<id>/dismantle` — log dismantling event
- `POST /assets/<id>/assign` — assign to user/site
- `POST /assets/<id>/return` — log return

### Scanning
- `GET /scan` — standalone scan page (scan → redirect to asset detail or create)
- `POST /api/lookup` — JSON: look up asset by serial number or barcode

### Sites
- `GET /sites` — list sites
- `GET /sites/<id>` — site inventory

### Tasks
- `GET /tasks` — task list sortable by due date
- `POST /tasks` — create task
- `POST /tasks/<id>/done` — mark done

### Admin
- `GET /admin/users` — user management
- `GET /admin/export` — CSV export

---

## 6. Implementation Phases

### Phase 1 — Foundation
- [ ] Project scaffold: Flask app factory, config, SQLAlchemy, Flask-Migrate
- [ ] Database models: users, sites, asset_types, assets, asset_events
- [ ] Auth: login, logout, role-based access
- [ ] Base template with Bootstrap 5 navbar

### Phase 2 — Core Asset Management
- [ ] Asset CRUD (create, list, detail, edit)
- [ ] Asset event logging (dismantle, move, assign, return)
- [ ] Site management pages
- [ ] Asset type management

### Phase 3 — Scanning
- [ ] Scan page with camera (QuaggaJS + html5-qrcode)
- [ ] `/api/lookup` endpoint
- [ ] Inline scanner widget on asset forms
- [ ] Mobile-friendly layout for field technicians

### Phase 4 — Due Dates & Tasks
- [ ] Due date field on assets and tasks
- [ ] Dashboard alerts (overdue, due within 7 days)
- [ ] Task CRUD with due date sorting
- [ ] Flask-Mail integration for due date reminders

### Phase 5 — Reporting & Polish
- [ ] Dashboard charts (Chart.js)
- [ ] CSV export
- [ ] Asset history page per asset
- [ ] Site inventory report

---

## 7. Project Directory Structure

```
netstock/
├── app/
│   ├── __init__.py          # app factory
│   ├── config.py
│   ├── models/
│   │   ├── user.py
│   │   ├── asset.py
│   │   ├── site.py
│   │   └── task.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── assets.py
│   │   ├── scan.py
│   │   ├── sites.py
│   │   ├── tasks.py
│   │   └── admin.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── assets/
│   │   ├── scan/
│   │   ├── sites/
│   │   └── tasks/
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── vendor/          # QuaggaJS, html5-qrcode
│   └── utils/
│       └── email.py
├── migrations/
├── tests/
├── plan.md
├── requirements.txt
├── .env.example
└── run.py
```

---

## 8. Key Libraries (requirements.txt)

```
Flask
Flask-SQLAlchemy
Flask-Migrate
Flask-Login
Flask-Bcrypt
Flask-WTF
Flask-Mail
python-dotenv
```

---

## 9. Open Questions / Decisions

- [ ] Will the app be deployed on a server or run locally?
- [ ] Should multiple users work simultaneously (concurrent sessions)?
- [ ] Are there specific barcode formats used on existing hardware labels?
- [ ] Should dismantled equipment generate a printable label/QR code?
- [ ] Do tasks belong to assets, to sites, or both?
