"""One timestamped frame shared by safety, API, history and WebSocket clients."""
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def generate_frame(simulator, run_id):
    s = simulator.state
    noise = simulator.random
    voltage = 22 + s.battery_charge * 0.075
    link = "REACQUIRING" if s.reacquire_remaining else ("LOST" if s.packet_loss > 65 else "DEGRADED" if s.packet_loss >= 5 else "CONNECTED")
    return {
        "timestamp": utc_now(), "run_id": run_id,
        "telemetry_sequence_number": s.sequence, "mission_elapsed_time": round(s.simulation_time, 2),
        "spacecraft_mode": s.mode, "link_status": link, "orbit_phase": s.orbit_phase,
        "orbit_progress": round((s.simulation_time % simulator.orbit_period) / simulator.orbit_period, 4),
        "orbit_number": int(s.simulation_time // simulator.orbit_period) + 1,
        "battery_voltage": round(voltage + noise.uniform(-0.015, 0.015), 3),
        "battery_current": round((s.solar_generation - s.power_consumption) / voltage, 3),
        "battery_charge_percent": round(s.battery_charge, 2),
        "solar_array_voltage": round(32 + noise.uniform(-0.1, 0.1) if s.solar_generation > 1 else 0, 2),
        "power_generation": round(s.solar_generation, 2), "power_consumption": round(s.power_consumption, 2),
        "battery_temperature": round(s.battery_temperature + noise.uniform(-0.04, 0.04), 2),
        "obc_temperature": round(s.obc_temperature + noise.uniform(-0.04, 0.04), 2),
        "payload_temperature": round(s.payload_temperature + noise.uniform(-0.04, 0.04), 2),
        "external_temperature": round(s.external_temperature, 2),
        "roll": round(s.roll, 3), "pitch": round(s.pitch, 3), "yaw": round(s.yaw, 3),
        "angular_velocity": round(s.angular_velocity, 3), "reaction_wheel_rpm": round(s.wheel_rpm, 1),
        "adcs_status": "DESATURATING" if s.desaturating_remaining else "UNSTABLE" if s.angular_velocity > 1.5 else "STABLE",
        "signal_strength": round(s.signal_strength + noise.uniform(-0.08, 0.08), 2),
        "packet_loss": round(s.packet_loss, 2), "uplink_status": link,
        "downlink_rate": round(512 * (1 - s.packet_loss / 100) if link != "REACQUIRING" else 0, 1),
        "payload_status": "ON" if s.payload_on else "OFF", "payload_power": s.payload_power,
        "data_buffer_usage": round(s.buffer_usage, 2), "cpu_load": round(s.cpu_load, 2),
        "memory_usage": round(s.memory_usage, 2), "storage_usage": round(s.storage_usage, 2),
        "watchdog_status": "HEALTHY", "secondary_processes": s.secondary_processes,
        "uptime": round(s.simulation_time, 2), "faults": list(s.faults),
    }
