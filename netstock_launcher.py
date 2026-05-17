"""
Inventory launcher — used as PyInstaller entry point.

When frozen: sets DATABASE_URL to <exe_dir>/inventory.db before any app
import so SQLAlchemy never writes into the ephemeral sys._MEIPASS temp dir.
Also handles first-run DB creation, seeding, port selection, and
auto-opening the browser.
"""
import os
import sys
import socket
import threading
import webbrowser
import time


def _exe_dir():
    """Return the directory that contains the running EXE (or run.py in dev)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _set_db_path():
    """Point DATABASE_URL at a file next to the EXE / project root."""
    if 'DATABASE_URL' not in os.environ:
        db_path = os.path.join(_exe_dir(), 'inventory.db')
        os.environ['DATABASE_URL'] = 'sqlite:///' + db_path


def _find_free_port(start=5000, end=5100):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return start


def _open_browser(url, delay=2.5):
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def _first_run_setup(app):
    """Create tables and seed admin user + reference data on first run."""
    from app import db, bcrypt
    from app.models.user import User
    from app.models.site import Site
    from app.models.asset import AssetType

    with app.app_context():
        db.create_all()

        # Schema migrations for existing databases
        from sqlalchemy import text
        cols = [r[1] for r in db.session.execute(text("PRAGMA table_info(assets)")).fetchall()]

        if 'component_id' not in cols:
            db.session.execute(text("ALTER TABLE assets ADD COLUMN component_id VARCHAR(50)"))
            db.session.commit()

        if 'conversion_fee' not in cols:
            db.session.execute(text("ALTER TABLE assets ADD COLUMN conversion_fee NUMERIC(5,2)"))
            db.session.commit()

        # Fill in placeholder component_id for any asset still missing one
        db.session.execute(text(
            "UPDATE assets SET component_id = 'SN-' || printf('%04d', abs(random() % 10000))"
            " WHERE component_id IS NULL OR component_id = ''"
        ))

        # Drop the legacy due_date column from assets if it still exists
        if 'due_date' in cols:
            db.session.execute(text("ALTER TABLE assets DROP COLUMN due_date"))

        db.session.commit()

        # Drop due_date from tasks if it still exists
        task_cols = [r[1] for r in db.session.execute(text("PRAGMA table_info(tasks)")).fetchall()]
        if 'due_date' in task_cols:
            db.session.execute(text("ALTER TABLE tasks DROP COLUMN due_date"))
            db.session.commit()

        if not User.query.first():
            print('[Inventory] First run detected — seeding database …')

            admin = User(
                name='Admin',
                email='admin@inventory.app',
                password_hash=bcrypt.generate_password_hash('admin1234').decode('utf-8'),
                role='admin',
            )
            db.session.add(admin)

            for name in ['Beit VaGan', 'Tel Aviv HQ', 'Haifa DC', 'Storage Warehouse']:
                db.session.add(Site(name=name))

            for name, category in [
                ('SFP Module', 'Networking'), ('Switch', 'Networking'),
                ('Router', 'Networking'), ('Patch Panel', 'Networking'),
                ('Firewall', 'Security'), ('Server', 'Compute'),
                ('UPS', 'Power'), ('Cable', 'Cabling'),
            ]:
                db.session.add(AssetType(name=name, category=category))

            db.session.commit()
            print('[Inventory] Seed complete. Login: admin@inventory.app / admin1234')


def main():
    # 1. Fix DB path BEFORE importing anything from the app package
    _set_db_path()

    # 2. When frozen, add sys._MEIPASS to sys.path so "app" package is found
    if getattr(sys, 'frozen', False):
        meipass = sys._MEIPASS  # type: ignore[attr-defined]
        if meipass not in sys.path:
            sys.path.insert(0, meipass)

    # 3. Create the Flask application
    from app import create_app
    flask_app = create_app()

    # 4. First-run DB initialisation + seed
    _first_run_setup(flask_app)

    # 5. Choose a free port and open the browser
    port = _find_free_port()
    url = f'http://127.0.0.1:{port}'
    print(f'[Inventory] Starting server on {url}')
    print('[Inventory] Press Ctrl+C to quit.')
    _open_browser(url)

    # 6. Run Flask (threaded so the browser-open thread doesn't block it)
    flask_app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
