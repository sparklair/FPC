"""Mission constants and adjustable demonstration limits (not flight limits)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'instance' / 'mission.db'}")
    HISTORY_SIZE = 120
    TICK_INTERVAL = 1.0
    ORBIT_PERIOD = 300.0
    SUNLIGHT_FRACTION = 0.65
    SEED = 42
    TESTING = False
    MAX_CONTENT_LENGTH = 4096


# parameter: subsystem, display label, warning, critical, hysteresis, direction, unit
LIMITS = {
    "battery_charge_percent": ("EPS", "Battery charge", 30, 15, 4, "low", "%"),
    "battery_voltage": ("EPS", "Battery voltage", 24, 22.5, 0.4, "low", "V"),
    "battery_temperature": ("THERMAL", "Battery temperature", 45, 55, 3, "high", "°C"),
    "obc_temperature": ("OBC", "OBC temperature", 70, 80, 4, "high", "°C"),
    "payload_temperature": ("PAYLOAD", "Payload temperature", 70, 85, 5, "high", "°C"),
    "reaction_wheel_rpm": ("ADCS", "Reaction wheel speed", 5500, 7200, 400, "high", "rpm"),
    "angular_velocity": ("ADCS", "Angular velocity", 1.5, 3.5, 0.3, "high", "°/s"),
    "packet_loss": ("COMMS", "Packet loss", 5, 20, 2, "high", "%"),
    "signal_strength": ("COMMS", "Signal strength", -95, -110, 4, "low", "dBm"),
    "cpu_load": ("OBC", "CPU load", 80, 95, 5, "high", "%"),
    "memory_usage": ("OBC", "Memory usage", 85, 95, 4, "high", "%"),
    "data_buffer_usage": ("PAYLOAD", "Data buffer", 80, 95, 5, "high", "%"),
}

FAULTS = {
    "BATTERY_DRAIN": ("EPS", "Progressive battery drain"),
    "PAYLOAD_OVERHEAT": ("PAYLOAD", "Payload thermal excursion"),
    "OBC_OVERHEAT": ("OBC", "On-board computer overheat"),
    "COMMUNICATION_LOSS": ("COMMS", "Telemetry link degradation"),
    "ADCS_INSTABILITY": ("ADCS", "Attitude control instability"),
}
