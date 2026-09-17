"""Local entry point: python app.py."""
import logging
import os

from spacecraft_control import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    app.extensions["mission"].start()
    try:
        app.extensions["socketio"].run(
            app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")),
            debug=False, use_reloader=False, allow_unsafe_werkzeug=True,
        )
    finally:
        app.extensions["mission"].stop()
