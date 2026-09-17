"""Single serialized mission controller shared by HTTP, sockets and one worker."""
import logging
import threading
import time
import uuid
from collections import deque
from copy import deepcopy

from ..config import FAULTS, LIMITS
from ..safety.actions import COMMAND_SUBSYSTEMS
from ..safety.engine import SafetyEngine
from ..telemetry.generator import generate_frame
from ..telemetry.simulator import Simulator
from .event_service import EventStore

logger = logging.getLogger(__name__)


class Mission:
    def __init__(self, app, socketio):
        self.socketio = socketio
        self.lock = threading.RLock()
        self.stop_signal = threading.Event()
        self.thread = None
        self.started_at = time.monotonic()
        self.interval = app.config["TICK_INTERVAL"]
        self.store = EventStore(app.config["DATABASE_URL"])
        self.simulator = Simulator(app.config["ORBIT_PERIOD"], app.config["SUNLIGHT_FRACTION"], app.config["SEED"])
        self.history = deque(maxlen=app.config["HISTORY_SIZE"])
        self.run_id = str(uuid.uuid4())
        self.safety = SafetyEngine(app.config.get("SAFETY_LIMITS", LIMITS), self)
        self.speed = 1.0
        self.paused = False
        self.demo = False
        self.demo_index = 0
        self.demo_next = 15.0
        self.demo_waiting = False
        self.error = None
        self.current = self.make_frame()
        self.history.append(deepcopy(self.current))
        self.event("INFO", "SYSTEM", "Mission initialized · simulated telemetry link established")

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_signal.clear()
            self.thread = threading.Thread(target=self._run, name="mission-simulator", daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_signal.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)

    def _run(self):
        while not self.stop_signal.wait(self.interval):
            try:
                self.tick()
            except Exception:
                logger.exception("Simulation step failed; worker remains available")
                with self.lock:
                    self.error = "Simulation step failed; see server log"
                    self.paused = True
                    self.publish("spacecraft_status_update", self.status())

    def tick(self):
        with self.lock:
            if self.paused:
                return
            # Safety runs at least once per simulated second even at 5×.
            # Playback speed changes simulated time, not protection latency.
            remaining = self.interval * self.speed
            while remaining > 1e-9:
                step = min(remaining, 1.0)
                old_phase = self.simulator.state.orbit_phase
                old_reacquiring = self.simulator.state.reacquire_remaining > 0
                self.simulator.step(step, record_frame=False)
                s = self.simulator.state
                if s.orbit_phase != old_phase:
                    self.event("INFO", "EPS", f"Orbit phase: {s.orbit_phase}")
                if old_reacquiring and not s.reacquire_remaining:
                    self.event("RECOVERY", "COMMS", "Antenna reacquisition completed · signal settling", incident_id=self.safety.incidents.get("COMMS"))
                self.safety.evaluate(generate_frame(self.simulator, self.run_id))
                self._demo_step()
                remaining -= step
            self.simulator.state.sequence += 1
            self.current = self.make_frame()
            self.history.append(deepcopy(self.current))
            self.broadcast()

    def make_frame(self):
        frame = generate_frame(self.simulator, self.run_id)
        rank = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}
        states = {name: "NORMAL" for name in ("EPS", "THERMAL", "ADCS", "COMMS", "PAYLOAD", "OBC")}
        for alarm in self.safety.active.values():
            subsystems = [alarm["subsystem"]]
            if "temperature" in alarm["parameter"]:
                subsystems.append("THERMAL")
            for subsystem in subsystems:
                if rank[alarm["severity"]] > rank[states[subsystem]]:
                    states[subsystem] = alarm["severity"]
        if not self.simulator.state.payload_on and states["PAYLOAD"] == "NORMAL":
            states["PAYLOAD"] = "OFFLINE"
        frame["subsystem_status"] = states
        return frame

    def status(self):
        s = self.simulator.state
        return {
            "spacecraft": "ONLINE", "mode": s.mode, "link": self.current["link_status"],
            "orbit_phase": s.orbit_phase, "simulation": "PAUSED" if self.paused else "RUNNING",
            "speed": self.speed, "auto_demo": self.demo, "demo_step": self.demo_index,
            "simulation_time": round(s.simulation_time, 2), "frames": s.sequence,
            "uptime": round(time.monotonic() - self.started_at, 1), "run_id": self.run_id,
            "active_alarms": len(self.safety.active), "faults": list(s.faults), "error": self.error,
        }

    def snapshot(self):
        with self.lock:
            return deepcopy({
                "telemetry": self.current, "history": list(self.history), "status": self.status(),
                "alarms": list(self.safety.active.values()), "events": self.store.entries("event"),
                "commands": self.store.entries("command"), "incidents": self.store.incidents(),
            })

    def publish(self, name, data):
        try:
            self.socketio.emit(name, data)
        except Exception:
            logger.exception("Socket emission failed: %s", name)

    def broadcast(self):
        self.publish("telemetry_update", self.current)
        self.publish("alarm_update", list(self.safety.active.values()))
        self.publish("spacecraft_status_update", self.status())
        self.publish("incident_update", self.store.incidents())

    def event(self, severity, subsystem, message, parameter=None, measured_value=None, threshold=None, automatic_action=None, incident_id=None):
        row = self.store.append("event", self.run_id, {
            "severity": severity, "subsystem": subsystem, "message": message, "parameter": parameter,
            "measured_value": measured_value, "threshold": threshold, "automatic_action": automatic_action,
            "simulation_time": round(self.simulator.state.simulation_time, 2),
        }, incident_id)
        self.publish("event_update", row)
        return row

    def execute(self, command, source="OPERATOR", reason="Operator request", incident_id=None):
        """Caller holds mission lock. All commands, including rejections, are audited."""
        s = self.simulator.state
        rejection = None
        if command == "PAYLOAD_ON" and (s.mode != "NOMINAL" or s.battery_charge <= 34 or s.payload_temperature >= 65 or s.obc_temperature >= 70 or self.safety.active):
            rejection = "Payload inhibited until nominal mode and all safety limits recover"
        if command == "RETURN_NOMINAL" and (self.safety.active or s.faults or s.battery_charge <= 34 or s.obc_temperature >= 66 or s.payload_temperature >= 65):
            rejection = "Nominal return inhibited: unresolved fault or safety limit"
        unchanged = (
            (command == "PAYLOAD_OFF" and not s.payload_on)
            or (command == "PAYLOAD_ON" and s.payload_on)
            or (command == "CPU_THROTTLE" and s.cpu_throttled)
            or (command == "ENTER_SAFE_MODE" and s.mode == "SAFE_MODE")
            or (command == "ENTER_POWER_SAVE" and s.mode in {"POWER_SAVE", "SAFE_MODE"})
            or (command == "COMMS_REACQUIRE" and s.reacquire_remaining > 0)
            or (command == "ADCS_DESATURATION" and s.desaturating_remaining > 0)
        )
        if source == "AUTO" and unchanged:
            return None
        if not rejection:
            if command in {"PAYLOAD_OFF", "ENTER_POWER_SAVE", "ENTER_SAFE_MODE"}:
                s.payload_on = False
                s.payload_power = 0
                s.faults.pop("PAYLOAD_OVERHEAT", None)
            if command == "PAYLOAD_ON":
                s.payload_on = True
                s.payload_power = 18
            elif command in {"ENTER_POWER_SAVE", "ENTER_SAFE_MODE"}:
                # POWER_SAVE must never downgrade an existing SAFE_MODE.
                if command == "ENTER_SAFE_MODE" or s.mode != "SAFE_MODE":
                    s.mode = "SAFE_MODE" if command == "ENTER_SAFE_MODE" else "POWER_SAVE"
                    s.mode_source = source
                s.cpu_throttled = True
                s.secondary_processes = False
                s.faults.pop("BATTERY_DRAIN", None)
                if command == "ENTER_SAFE_MODE":
                    s.faults.pop("OBC_OVERHEAT", None)
                    s.faults.pop("ADCS_INSTABILITY", None)
                    s.desaturating_remaining = 18
            elif command == "CPU_THROTTLE":
                s.cpu_throttled = True
                s.secondary_processes = False
            elif command == "RETURN_NOMINAL":
                s.mode = "NOMINAL"
                s.mode_source = source
                s.cpu_throttled = False
                s.secondary_processes = True
            elif command == "COMMS_REACQUIRE":
                s.reacquire_remaining = 8
            elif command == "ADCS_DESATURATION":
                s.desaturating_remaining = 18
                s.faults.pop("ADCS_INSTABILITY", None)
        subsystem = COMMAND_SUBSYSTEMS[command]
        row = self.store.append("command", self.run_id, {
            "source": source, "command": command, "subsystem": subsystem, "reason": reason,
            "result": "REJECTED" if rejection else "NO_CHANGE" if unchanged else "EXECUTED",
            "detail": rejection or "Applied to simulated spacecraft", "simulation_time": round(s.simulation_time, 2),
        }, incident_id)
        self.publish("command_update", row)
        self.event("AUTO_ACTION" if source == "AUTO" else "COMMAND", subsystem,
                   f"{command} · {row['result']} · {rejection or reason}", automatic_action=command if source == "AUTO" else None, incident_id=incident_id)
        return row

    def operator_command(self, command):
        with self.lock:
            result = self.execute(command)
            self.current = self.make_frame()
            self.broadcast()
            return result

    def inject_fault(self, fault, source="OPERATOR"):
        with self.lock:
            s = self.simulator.state
            if fault in s.faults:
                raise ValueError("This fault is already active")
            if fault == "BATTERY_DRAIN" and s.mode != "NOMINAL":
                raise ValueError("Return to nominal mode before injecting battery drain")
            if fault == "PAYLOAD_OVERHEAT" and not s.payload_on:
                raise ValueError("Enable payload in nominal mode before injecting payload overheat")
            if fault == "OBC_OVERHEAT" and s.mode == "SAFE_MODE":
                raise ValueError("Return to nominal mode before injecting OBC overheat")
            s.faults[fault] = 0.01
            subsystem, title = FAULTS[fault]
            self.event("INFO", subsystem, f"Fault injected: {title} · {source}")
            if source == "OPERATOR":
                self.current = self.make_frame()
                self.broadcast()

    def clear_faults(self):
        with self.lock:
            self.simulator.state.faults.clear()
            self.event("COMMAND", "SYSTEM", "Fault sources cleared · physical state will recover gradually")
            self.current = self.make_frame()
            self.broadcast()

    def reset(self):
        with self.lock:
            self.safety.clear("Incident closed by simulation reset")
            self.simulator.reset()
            self.run_id = str(uuid.uuid4())
            self.history.clear()
            self.paused = False
            self.speed = 1.0
            self.demo = False
            self.demo_index = 0
            self.demo_next = 15.0
            self.demo_waiting = False
            self.error = None
            self.current = self.make_frame()
            self.history.append(deepcopy(self.current))
            self.event("COMMAND", "SYSTEM", "Simulation reset · new run initialized · journal retained")
            self.publish("simulation_reset", self.snapshot())

    def configure(self, action, value=None):
        with self.lock:
            if action == "reset":
                self.reset()
            elif action == "pause":
                self.paused = True
            elif action == "resume":
                self.paused = False
                self.error = None
            elif action == "speed":
                self.speed = float(value)
            elif action == "demo":
                self.demo = value
                self.demo_next = self.simulator.state.simulation_time + 15
                self.demo_waiting = bool(self.simulator.state.faults or self.safety.active)
            if action != "reset":
                self.event("COMMAND", "SYSTEM", f"Simulation {action}" + (f": {value}" if value is not None else ""))
            self.broadcast()
            return self.status()

    def _demo_step(self):
        if not self.demo:
            return
        s = self.simulator.state
        if self.safety.active or s.faults or s.mode != "NOMINAL":
            return
        if self.demo_waiting:
            self.demo_waiting = False
            self.demo_next = s.simulation_time + 20
            self.event("RECOVERY", "SYSTEM", "Auto demo · scenario recovered; observing nominal operation")
            if not s.payload_on:
                self.execute("PAYLOAD_ON", "AUTO", "Auto demo: resume science after recovery")
            return
        if s.simulation_time >= self.demo_next:
            scenarios = ["PAYLOAD_OVERHEAT", "COMMUNICATION_LOSS", "ADCS_INSTABILITY", "OBC_OVERHEAT", "BATTERY_DRAIN"]
            fault = scenarios[self.demo_index % len(scenarios)]
            if fault == "PAYLOAD_OVERHEAT" and not s.payload_on:
                result = self.execute("PAYLOAD_ON", "AUTO", "Auto demo: prepare payload")
                if result and result["result"] == "REJECTED":
                    return
            self.inject_fault(fault, "AUTO DEMO")
            self.demo_index += 1
            self.demo_waiting = True
