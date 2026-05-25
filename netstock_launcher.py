"""
Inventory launcher — used as PyInstaller entry point.

Connects to MongoDB Atlas. On first run, seeds the default admin user,
sites, and asset types. Then starts the Flask server and opens the browser.
"""
import os
import sys
import socket
import threading
import webbrowser
import time


def _exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    from dotenv import load_dotenv
    env_path = os.path.join(_exe_dir(), '.env')
    load_dotenv(env_path, override=False)

    smtp_email = os.environ.get('SMTP_EMAIL', '')
    smtp_password = os.environ.get('SMTP_PASSWORD', '')
    if smtp_email and smtp_password:
        print(f'[Inventory] SMTP loaded: {smtp_email}')
    else:
        print('[Inventory] Warning: SMTP_EMAIL or SMTP_PASSWORD not found in .env')


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
    from app import bcrypt
    from app.models.user import User
    from app.models.site import Site
    from app.models.asset import AssetType
    from app.models.settings import AppSetting

    with app.app_context():
        # Ensure default USD rate setting exists
        if not AppSetting.objects(key='usd_rate').first():
            AppSetting(key='usd_rate', value='3.0').save()

        if not User.objects.first():
            print('[Inventory] First run detected — seeding database …')

            User(
                name='Admin',
                email='admin@inventory.app',
                password_hash=bcrypt.generate_password_hash('admin1234').decode('utf-8'),
                role='admin',
            ).save()

            for name in ['Beit VaGan', 'Tel Aviv HQ', 'Haifa DC', 'Storage Warehouse']:
                Site(name=name).save()

            for name in [
                'Routers', 'Aggregation', 'Access switches', 'Sfp', 'Cards',
                'Power supplies', 'Power cords', 'Console cables',
            ]:
                AssetType(name=name).save()

            print('[Inventory] Seed complete. Login: admin@inventory.app / admin1234')


def main():
    _load_dotenv()

    if getattr(sys, 'frozen', False):
        meipass = sys._MEIPASS  # type: ignore[attr-defined]
        if meipass not in sys.path:
            sys.path.insert(0, meipass)

    from app import create_app
    flask_app = create_app()

    _first_run_setup(flask_app)

    port = _find_free_port()
    url  = f'http://127.0.0.1:{port}'
    print(f'[Inventory] Starting server on {url}')
    print('[Inventory] Press Ctrl+C to quit.')
    _open_browser(url)

    flask_app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
