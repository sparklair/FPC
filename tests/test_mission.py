"""Behavioral checks for the full simulation → protection → recovery loop."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from spacecraft_control import create_app
from spacecraft_control.config import LIMITS
from spacecraft_control.safety.rules import Rule
from spacecraft_control.telemetry.simulator import Simulator


@pytest.mark.parametrize("fault,expected", [
    ("BATTERY_DRAIN", {"PAYLOAD_OFF", "ENTER_POWER_SAVE", "RETURN_NOMINAL"}),
    ("PAYLOAD_OVERHEAT", {"PAYLOAD_OFF"}),
    ("OBC_OVERHEAT", {"CPU_THROTTLE", "ENTER_SAFE_MODE", "RETURN_NOMINAL"}),
    ("COMMUNICATION_LOSS", {"COMMS_REACQUIRE"}),
    ("ADCS_INSTABILITY", {"ADCS_DESATURATION"}),
])
@pytest.mark.parametrize("speed", [0.5, 1, 2, 5])
def test_fault_closed_loop(mission, fault, expected, speed):
    mission.configure("speed", speed)
    before = mission.current.copy()
    mission.inject_fault(fault)
    # Injection adds a cause; it does not teleport a measured parameter.
    for key in ("battery_charge_percent", "payload_temperature", "obc_temperature", "packet_loss", "reaction_wheel_rpm"):
        assert abs(mission.current[key] - before[key]) < 0.1
    warning_seen = critical_seen = False
    frames = []
    for _ in range(int(450 / speed)):
        mission.tick()
        frames.append(mission.current.copy())
        severities = set(mission.safety.states.values())
        warning_seen |= "WARNING" in severities
        critical_seen |= "CRITICAL" in severities
        if critical_seen and not mission.safety.active and not mission.simulator.state.faults:
            break
    assert warning_seen and critical_seen
    assert not mission.safety.active
    assert not mission.simulator.state.faults
    commands = mission.store.entries("command", 500)
    names = [row["command"] for row in commands]
    assert expected <= set(names)
    assert len(names) == len(set(names)), "Protection must not spam commands"
    assert all(row["result"] == "EXECUTED" for row in commands)
    assert mission.current["spacecraft_mode"] == "NOMINAL"
    assert all(row["status"] == "RESOLVED" for row in mission.store.incidents())
    assert all(row["status"] == "CLEARED" for row in mission.store.alarm_history())
    event_severities = {row["severity"] for row in mission.store.entries("event", 500)}
    assert {"WARNING", "CRITICAL", "AUTO_ACTION", "RECOVERY"} <= event_severities
    if fault == "PAYLOAD_OVERHEAT":
        assert mission.current["payload_power"] == 0
        # At 5× the safety loop can detect and mitigate a peak between UI frames.
        assert any(event["parameter"] == "payload_temperature" and event["severity"] == "CRITICAL" and event["measured_value"] >= 85
                   for event in mission.store.entries("event", 500))
        assert mission.current["payload_temperature"] < 65
    if fault == "OBC_OVERHEAT":
        assert any(f["spacecraft_mode"] == "SAFE_MODE" for f in frames)
        assert min(f["cpu_load"] for f in frames) < 20
    if fault == "COMMUNICATION_LOSS":
        assert any(f["link_status"] == "REACQUIRING" for f in frames)
        assert mission.current["link_status"] == "CONNECTED"


def test_nominal_orbits_have_no_spurious_alarms(mission):
    phases = set()
    charge = []
    for _ in range(1200):
        mission.tick()
        phases.add(mission.current["orbit_phase"])
        charge.append(mission.current["battery_charge_percent"])
    assert phases == {"SUNLIGHT", "ECLIPSE"}
    assert 60 < min(charge) < 85
    assert max(charge) <= 100
    assert not mission.store.entries("command")
    assert not mission.store.incidents()
    assert len(mission.history) == 120


def test_hysteresis_at_both_severity_boundaries():
    rule = Rule("obc_temperature", *LIMITS["obc_temperature"])
    level = rule.severity(80.1)
    assert level == "CRITICAL"
    for value in [79.9, 80.1, 79.8, 80.2, 77.0]:
        level = rule.severity(value, level)
        assert level == "CRITICAL"
    assert rule.severity(75.9, level) == "WARNING"
    assert rule.severity(69.9, "WARNING") == "WARNING"
    assert rule.severity(65.9, "WARNING") == "NORMAL"
    battery = Rule("battery_charge_percent", *LIMITS["battery_charge_percent"])
    assert battery.severity(15) == "CRITICAL"
    assert battery.severity(18, "CRITICAL") == "CRITICAL"
    assert battery.severity(19, "CRITICAL") == "WARNING"
    assert battery.severity(33, "WARNING") == "WARNING"
    assert battery.severity(34, "WARNING") == "NORMAL"


def test_load_power_temperature_coupling():
    on, off = Simulator(), Simulator()
    off.state.payload_on = False
    for _ in range(60):
        on.step(1)
        off.step(1)
    assert on.state.power_consumption > off.state.power_consumption + 18
    assert on.state.payload_temperature > off.state.payload_temperature + 10
    assert off.state.battery_charge > on.state.battery_charge


def test_pause_speed_reset_and_audit_retention(mission):
    mission.inject_fault("PAYLOAD_OVERHEAT")
    for _ in range(22):
        mission.tick()
    assert mission.safety.active
    mission.configure("pause")
    before = mission.snapshot()
    mission.tick()
    assert mission.current == before["telemetry"]
    mission.configure("speed", 5)
    mission.configure("resume")
    mission.tick()
    assert mission.current["mission_elapsed_time"] == before["telemetry"]["mission_elapsed_time"] + 5
    run_id = mission.run_id
    incident_ids = {row["id"] for row in mission.store.incidents()}
    mission.reset()
    assert mission.run_id != run_id
    assert mission.current["telemetry_sequence_number"] == 0
    assert mission.current["payload_status"] == "ON"
    assert mission.current["battery_charge_percent"] == 84
    assert not mission.safety.active and not mission.simulator.state.faults
    assert len(mission.history) == 1
    assert all(row["status"] == "RESET" for row in mission.store.incidents() if row["id"] in incident_ids)
    assert len(mission.store.entries("event")) > len(before["events"])


def test_clear_faults_preserves_temperature_and_allows_natural_recovery(mission):
    mission.inject_fault("PAYLOAD_OVERHEAT")
    for _ in range(22):
        mission.tick()
    temperature = mission.current["payload_temperature"]
    mission.clear_faults()
    assert abs(mission.current["payload_temperature"] - temperature) < 0.1
    assert mission.safety.active
    for _ in range(60):
        mission.tick()
    assert not mission.safety.active
    assert mission.current["payload_temperature"] < temperature


def test_operator_interlocks_and_safe_mode_priority(mission):
    mission.operator_command("ENTER_SAFE_MODE")
    mission.operator_command("ENTER_POWER_SAVE")
    assert mission.current["spacecraft_mode"] == "SAFE_MODE"
    assert mission.operator_command("PAYLOAD_ON")["result"] == "REJECTED"
    with pytest.raises(ValueError, match="nominal"):
        mission.inject_fault("BATTERY_DRAIN")
    for _ in range(10):
        mission.tick()
    assert mission.current["spacecraft_mode"] == "SAFE_MODE", "Operator mode must not auto-release"
    assert mission.operator_command("RETURN_NOMINAL")["result"] == "EXECUTED"
    assert mission.operator_command("PAYLOAD_ON")["result"] == "EXECUTED"
    mission.inject_fault("OBC_OVERHEAT")
    assert mission.operator_command("RETURN_NOMINAL")["result"] == "REJECTED"


def test_repeat_fault_rearms_protection(mission):
    for _ in range(2):
        mission.inject_fault("COMMUNICATION_LOSS")
        for _ in range(80):
            mission.tick()
        assert not mission.safety.active
    assert len(mission.store.entries("command")) == 2
    assert len(mission.store.incidents()) == 2


def test_combined_faults_recover_without_mode_downgrade(mission):
    for fault in ("BATTERY_DRAIN", "OBC_OVERHEAT", "PAYLOAD_OVERHEAT", "ADCS_INSTABILITY", "COMMUNICATION_LOSS"):
        mission.inject_fault(fault)
    for _ in range(500):
        mission.tick()
    assert not mission.safety.active
    assert not mission.simulator.state.faults
    assert mission.current["spacecraft_mode"] == "NOMINAL"


def test_auto_demo_completes_all_five_scenarios(mission):
    mission.configure("demo", True)
    for _ in range(1800):
        mission.tick()
        if mission.demo_index >= 5 and not mission.demo_waiting:
            break
    assert mission.demo_index == 5
    assert not mission.safety.active
    assert mission.current["spacecraft_mode"] == "NOMINAL"
    commands = {row["command"] for row in mission.store.entries("command", 500)}
    assert {"COMMS_REACQUIRE", "ADCS_DESATURATION", "CPU_THROTTLE", "ENTER_SAFE_MODE", "ENTER_POWER_SAVE"} <= commands
    mission.configure("demo", False)
    index = mission.demo_index
    for _ in range(50):
        mission.tick()
    assert mission.demo_index == index


def test_persistence_and_restart_closes_abandoned_incidents(tmp_path):
    config = {"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path / 'durable.db'}"}
    first = create_app(config).extensions["mission"]
    first.inject_fault("PAYLOAD_OVERHEAT")
    for _ in range(25):
        first.tick()
    first.operator_command("PAYLOAD_OFF")
    commands = first.store.entries("command")
    first.store.engine.dispose()
    second = create_app(config).extensions["mission"]
    assert second.store.entries("command") == commands
    assert second.store.incidents()[0]["status"] == "INTERRUPTED"
    assert not second.safety.active
    assert all(row["status"] == "CLEARED" for row in second.store.alarm_history())
    second.store.engine.dispose()


def test_serialized_concurrent_ticks_and_commands(mission):
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(mission.tick) for _ in range(30)]
        futures += [pool.submit(mission.operator_command, "PAYLOAD_OFF") for _ in range(5)]
        for future in futures:
            future.result()
    assert mission.current["telemetry_sequence_number"] == 30
    assert mission.current["payload_status"] == "OFF"
    assert len(mission.store.entries("command")) == 5
