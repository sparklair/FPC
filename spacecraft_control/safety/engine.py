from .actions import PROTECTION
from .rules import Rule


class SafetyEngine:
    def __init__(self, limits, mission):
        self.rules = {key: Rule(key, *spec) for key, spec in limits.items()}
        self.mission = mission
        self.states = {key: "NORMAL" for key in self.rules}
        self.active = {}
        self.incidents = {}
        self.handled = set()

    def evaluate(self, frame):
        pending = []
        for parameter, rule in self.rules.items():
            value = frame[parameter]
            previous = self.states[parameter]
            severity = rule.severity(value, previous)
            if severity != previous:
                self._transition(rule, previous, severity, value)
            if severity != "NORMAL":
                self.active[parameter]["measured_value"] = value
            if severity == "CRITICAL" and parameter not in self.handled:
                pending.append((parameter, rule))
                self.handled.add(parameter)
            if severity == "NORMAL":
                self.handled.discard(parameter)

        issued = set()
        for parameter, rule in pending:
            for command in PROTECTION.get(parameter, []):
                if command not in issued:
                    self.mission.execute(command, "AUTO", f"{rule.label} critical: {frame[parameter]:.2f} {rule.unit}", self.incidents.get(rule.subsystem))
                    issued.add(command)

        # Escalation is independent of threshold transitions and cannot be masked
        # by an earlier, less restrictive action in another subsystem.
        s = self.mission.simulator.state
        if frame["obc_temperature"] >= 90 and s.mode != "SAFE_MODE":
            self.mission.execute("ENTER_SAFE_MODE", "AUTO", "OBC heating continues after CPU throttling", self.incidents.get("OBC"))
        if (frame["reaction_wheel_rpm"] >= 9000 or frame["angular_velocity"] >= 5.5) and s.mode != "SAFE_MODE":
            self.mission.execute("ENTER_SAFE_MODE", "AUTO", "Severe attitude excursion", self.incidents.get("ADCS"))

        for subsystem, incident_id in list(self.incidents.items()):
            if not any(alarm["subsystem"] == subsystem for alarm in self.active.values()):
                self.mission.store.close_incident(incident_id)
                self.mission.event("RECOVERY", subsystem, "All parameters nominal · incident resolved", incident_id=incident_id)
                del self.incidents[subsystem]
        if not self.active and not s.faults:
            if s.mode != "NOMINAL" and s.mode_source == "AUTO":
                self.mission.execute("RETURN_NOMINAL", "AUTO", "Safety limits recovered; autonomous nominal return permitted")
            elif s.mode == "NOMINAL" and s.cpu_throttled:
                s.cpu_throttled = False
                s.secondary_processes = True
                self.mission.event("RECOVERY", "OBC", "Thermal protection released; secondary processes restored")

    def _transition(self, rule, previous, severity, value):
        mission = self.mission
        subsystem = rule.subsystem
        if subsystem not in self.incidents and severity != "NORMAL":
            title = {"PAYLOAD": "Payload thermal excursion", "EPS": "Electrical power excursion", "OBC": "On-board computer anomaly", "ADCS": "Attitude control excursion", "COMMS": "Communications degradation", "THERMAL": "Thermal control excursion"}[subsystem]
            self.incidents[subsystem] = mission.store.open_incident(mission.run_id, subsystem, title)
        incident_id = self.incidents.get(subsystem)
        old_alarm = self.active.get(rule.parameter, {})
        alarm_id = mission.store.alarm_transition(mission.run_id, rule, severity, value, incident_id, old_alarm.get("id"))
        self.states[rule.parameter] = severity
        recovering = severity == "NORMAL" or (previous == "CRITICAL" and severity == "WARNING")
        if severity == "NORMAL":
            self.active.pop(rule.parameter, None)
        else:
            self.active[rule.parameter] = {
                "id": alarm_id, "parameter": rule.parameter, "label": rule.label, "subsystem": subsystem,
                "severity": severity, "status": "ACTIVE", "measured_value": value,
                "threshold": rule.threshold(severity), "unit": rule.unit, "direction": rule.direction,
                "incident_id": incident_id,
            }
        message = f"{rule.label} {previous} → {severity}: {value:.2f} {rule.unit}"
        mission.event("RECOVERY" if recovering else severity, subsystem, message,
                      parameter=rule.parameter, measured_value=value, threshold=rule.threshold(severity), incident_id=incident_id)

    def clear(self, reason):
        for parameter, alarm in list(self.active.items()):
            rule = self.rules[parameter]
            self.mission.store.alarm_transition(self.mission.run_id, rule, "NORMAL", alarm["measured_value"], alarm["incident_id"], alarm["id"])
        for subsystem, incident_id in self.incidents.items():
            self.mission.store.close_incident(incident_id, "RESET")
            self.mission.event("INFO", subsystem, reason, incident_id=incident_id)
        self.active.clear()
        self.incidents.clear()
        self.handled.clear()
        self.states = {key: "NORMAL" for key in self.rules}
