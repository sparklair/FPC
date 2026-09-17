"""Protective commands selected on a critical transition."""
PROTECTION = {
    "battery_charge_percent": ["PAYLOAD_OFF", "ENTER_POWER_SAVE"],
    "battery_voltage": ["PAYLOAD_OFF", "ENTER_POWER_SAVE"],
    "battery_temperature": ["PAYLOAD_OFF", "ENTER_SAFE_MODE"],
    "payload_temperature": ["PAYLOAD_OFF"],
    "obc_temperature": ["CPU_THROTTLE"],
    "cpu_load": ["CPU_THROTTLE"],
    "memory_usage": ["CPU_THROTTLE"],
    "packet_loss": ["COMMS_REACQUIRE"],
    "signal_strength": ["COMMS_REACQUIRE"],
    "reaction_wheel_rpm": ["ADCS_DESATURATION"],
    "angular_velocity": ["ADCS_DESATURATION"],
    "data_buffer_usage": ["PAYLOAD_OFF"],
}

COMMAND_SUBSYSTEMS = {
    "PAYLOAD_ON": "PAYLOAD", "PAYLOAD_OFF": "PAYLOAD",
    "ENTER_POWER_SAVE": "EPS", "ENTER_SAFE_MODE": "OBC", "RETURN_NOMINAL": "OBC",
    "COMMS_REACQUIRE": "COMMS", "ADCS_DESATURATION": "ADCS", "CPU_THROTTLE": "OBC",
}
OPERATOR_COMMANDS = set(COMMAND_SUBSYSTEMS) - {"CPU_THROTTLE"}
