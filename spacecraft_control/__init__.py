import atexit
from pathlib import Path

from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from .config import Config
from .routes.api import api
from .routes.views import views
from .services.telemetry_service import Mission


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    url = app.config["DATABASE_URL"]
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    socketio = SocketIO(app, async_mode="threading", logger=False, engineio_logger=False)
    controller = Mission(app, socketio)
    app.extensions["mission"] = controller
    app.register_blueprint(api)
    app.register_blueprint(views)

    @socketio.on("connect")
    def connected(auth=None):
        with controller.lock:
            socketio.emit("initial_state", controller.snapshot(), to=request.sid)

    @app.errorhandler(413)
    def payload_too_large(_error):
        return jsonify(error="Request body exceeds 4 KB"), 413

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    atexit.register(controller.stop)
    return app
