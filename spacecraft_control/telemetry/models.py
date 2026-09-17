from dataclasses import dataclass, field


@dataclass
class SpacecraftState:
    simulation_time: float = 0.0
    sequence: int = 0
    mode: str = "NOMINAL"
    mode_source: str = "AUTO"
    payload_on: bool = True
    cpu_throttled: bool = False
    secondary_processes: bool = True
    battery_charge: float = 84.0
    battery_temperature: float = 24.0
    payload_temperature: float = 38.0
    obc_temperature: float = 43.0
    external_temperature: float = 8.0
    power_consumption: float = 43.0
    solar_generation: float = 78.0
    payload_power: float = 18.0
    cpu_load: float = 36.0
    memory_usage: float = 42.0
    storage_usage: float = 28.0
    buffer_usage: float = 18.0
    roll: float = 0.12
    pitch: float = -0.08
    yaw: float = 0.21
    angular_velocity: float = 0.08
    wheel_rpm: float = 2300.0
    signal_strength: float = -68.0
    packet_loss: float = 0.2
    reacquire_remaining: float = 0.0
    desaturating_remaining: float = 0.0
    orbit_phase: str = "SUNLIGHT"
    faults: dict[str, float] = field(default_factory=dict)
