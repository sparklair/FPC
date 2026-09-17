"""Time-integrated, coupled demonstration physics. No network or database access."""
import math
import random

from .models import SpacecraftState


def approach(value, target, rate, dt):
    return target + (value - target) * math.exp(-rate * dt)


def clamp(value, low, high):
    return max(low, min(high, value))


class Simulator:
    def __init__(self, orbit_period=300.0, sunlight_fraction=0.65, seed=42):
        self.orbit_period = orbit_period
        self.sunlight_fraction = sunlight_fraction
        self.seed = seed
        self.reset()

    def reset(self):
        self.state = SpacecraftState()
        self.random = random.Random(self.seed)

    def step(self, dt, record_frame=True):
        """Use <=0.5 s integration steps at every playback speed."""
        remaining = dt
        while remaining > 1e-9:
            step = min(remaining, 0.5)
            self._integrate(step)
            remaining -= step
        if record_frame:
            self.state.sequence += 1

    def _integrate(self, dt):
        s = self.state
        s.simulation_time += dt
        for fault in s.faults:
            s.faults[fault] += dt
        phase = (s.simulation_time % self.orbit_period) / self.orbit_period
        s.orbit_phase = "SUNLIGHT" if phase < self.sunlight_fraction else "ECLIPSE"
        sunlight = s.orbit_phase == "SUNLIGHT"
        s.solar_generation = approach(s.solar_generation, 78 + 4 * math.sin(phase * math.tau) if sunlight else 0, 0.3, dt)
        s.payload_power = 18.0 if s.payload_on else 0.0
        cpu_target = 36 + (10 if s.payload_on else 0)
        if s.cpu_throttled or s.mode != "NOMINAL":
            cpu_target = 13 if s.mode == "SAFE_MODE" else 21
        s.cpu_load = approach(s.cpu_load, cpu_target + 3 * math.sin(s.simulation_time / 11), 0.18, dt)
        drain = min(s.faults.get("BATTERY_DRAIN", 0) * 12, 350)
        s.power_consumption = 14 + s.payload_power + s.cpu_load * 0.24 + (4 if s.secondary_processes else 1) + drain
        net_power = s.solar_generation - s.power_consumption
        # Small equivalent battery accelerates energy dynamics for a short demo.
        s.battery_charge = clamp(s.battery_charge + net_power / (4.5 * 3600) * 100 * dt, 0, 100)
        s.battery_temperature = approach(s.battery_temperature, 23 + abs(net_power) * 0.05, 0.025, dt)
        s.external_temperature = approach(s.external_temperature, 22 if sunlight else -55, 0.025, dt)
        payload_heat = min(s.faults.get("PAYLOAD_OVERHEAT", 0) * 0.24, 3.2) if s.payload_on else 0
        s.payload_temperature = approach(s.payload_temperature, 24 + s.payload_power * 0.9, 0.045, dt) + payload_heat * dt
        obc_heat = min(s.faults.get("OBC_OVERHEAT", 0) * 0.22, 3.4)
        if s.cpu_throttled:
            obc_heat *= 0.65  # Residual heat can require escalation to SAFE_MODE.
        s.obc_temperature = approach(s.obc_temperature, 28 + s.cpu_load * 0.4, 0.025, dt) + obc_heat * dt
        s.memory_usage = approach(s.memory_usage, 31 + s.cpu_load * 0.3, 0.04, dt)

        if s.reacquire_remaining > 0:
            s.reacquire_remaining = max(0, s.reacquire_remaining - dt)
            if s.reacquire_remaining == 0:
                s.faults.pop("COMMUNICATION_LOSS", None)
        comm_age = s.faults.get("COMMUNICATION_LOSS", 0)
        loss_target = min(90, comm_age * 2.3) if comm_age else 0.25
        s.packet_loss = clamp(approach(s.packet_loss, loss_target, 0.22, dt), 0, 100)
        s.signal_strength = approach(s.signal_strength, -68 - s.packet_loss * 0.7, 0.2, dt)
        link_good = s.packet_loss < 20 and s.reacquire_remaining == 0
        s.buffer_usage = clamp(s.buffer_usage + ((0.11 if s.payload_on else 0) - (0.17 if link_good else 0)) * dt, 0, 100)
        s.storage_usage = clamp(s.storage_usage + (0.001 if s.payload_on else -0.001) * dt, 0, 100)

        instability = min(s.faults.get("ADCS_INSTABILITY", 0) * 0.1, 1)
        if s.desaturating_remaining > 0:
            s.desaturating_remaining = max(0, s.desaturating_remaining - dt)
            s.wheel_rpm = approach(s.wheel_rpm, 1800, 0.22, dt)
            s.angular_velocity = approach(s.angular_velocity, 0.08, 0.28, dt)
        elif instability:
            s.wheel_rpm = min(11000, s.wheel_rpm + 340 * instability * dt)
            s.angular_velocity = min(8, s.angular_velocity + 0.17 * instability * dt)
        else:
            s.wheel_rpm = approach(s.wheel_rpm, 2300 + 140 * math.sin(s.simulation_time / 18), 0.08, dt)
            s.angular_velocity = approach(s.angular_velocity, 0.08, 0.14, dt)
        for axis, offset in (("roll", 0), ("pitch", 2), ("yaw", 4)):
            target = math.sin(s.simulation_time / 22 + offset) * (0.25 + s.angular_velocity * 2)
            setattr(s, axis, approach(getattr(s, axis), target, 0.2, dt))
