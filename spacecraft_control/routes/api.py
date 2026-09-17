from flask import Blueprint, current_app, jsonify, request

from ..config import FAULTS
from ..safety.actions import OPERATOR_COMMANDS

api = Blueprint("api", __name__, url_prefix="/api")


def mission():
    return current_app.extensions["mission"]


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required")
    return data


def pagination():
    try:
        limit = int(request.args.get("limit", 100))
        before = int(request.args["before"]) if "before" in request.args else None
    except ValueError as exc:
        raise ValueError("limit and before must be integers") from exc
    if not 1 <= limit <= 500 or (before is not None and before < 1):
        raise ValueError("limit must be 1–500; before must be positive")
    return limit, before


@api.errorhandler(ValueError)
def invalid_request(error):
    return jsonify(error=str(error)), 400


@api.get("/telemetry/current")
def current():
    with mission().lock:
        return jsonify(mission().current)


@api.get("/telemetry/history")
def history():
    with mission().lock:
        return jsonify(list(mission().history))


@api.get("/events")
def events():
    limit, before = pagination()
    return jsonify(mission().store.entries("event", limit, before))


@api.get("/commands")
def commands():
    limit, before = pagination()
    return jsonify(mission().store.entries("command", limit, before))


@api.get("/alarms")
def alarms():
    with mission().lock:
        if request.args.get("history") == "true":
            limit, _ = pagination()
            return jsonify(mission().store.alarm_history(limit))
        return jsonify(list(mission().safety.active.values()))


@api.get("/incidents")
def incidents():
    return jsonify(mission().store.incidents())


@api.get("/incidents/<int:incident_id>")
def incident_timeline(incident_id):
    return jsonify(mission().store.entries("event", limit=500, incident_id=incident_id)[::-1])


@api.get("/status")
def status():
    with mission().lock:
        return jsonify(mission().status())


@api.get("/snapshot")
def snapshot():
    return jsonify(mission().snapshot())


@api.post("/command")
def command():
    name = body().get("command")
    if not isinstance(name, str) or name not in OPERATOR_COMMANDS:
        raise ValueError("Unknown command. Allowed: " + ", ".join(sorted(OPERATOR_COMMANDS)))
    result = mission().operator_command(name)
    return jsonify(result), 409 if result["result"] == "REJECTED" else 200


@api.post("/fault/inject")
def inject():
    fault = body().get("fault")
    if not isinstance(fault, str) or fault not in FAULTS:
        raise ValueError("Unknown fault. Allowed: " + ", ".join(FAULTS))
    mission().inject_fault(fault)
    return jsonify(ok=True, fault=fault)


@api.post("/fault/reset")
def clear_faults():
    mission().clear_faults()
    return jsonify(ok=True)


@api.post("/simulation")
def simulation():
    data = body()
    action, value = data.get("action"), data.get("value")
    if not isinstance(action, str) or action not in {"pause", "resume", "reset", "speed", "demo"}:
        raise ValueError("Unknown simulation action")
    if action == "speed" and (type(value) not in (int, float) or value not in (0.5, 1, 2, 5)):
        raise ValueError("Speed must be 0.5, 1, 2 or 5")
    if action == "demo" and not isinstance(value, bool):
        raise ValueError("Demo value must be a boolean")
    return jsonify(mission().configure(action, value))
