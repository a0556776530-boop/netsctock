from gevent import monkey
monkey.patch_all()

from app import create_app, socketio  # noqa: E402

app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
