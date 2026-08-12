import pytest

from clodbot.cli import parse_demo_phrase
from clodbot.core.enums import SafetyStatus, WorkerAction
from clodbot.core.world_state import MachineState
from clodbot.safety import SafetyEngine
from clodbot.simulation import IndustrialMachineSimulator, InvalidTransition


def safe_maintenance_state(**changes):
    state = MachineState(lockout_applied=True, lockout_verified=True)
    return state.evolve(**changes)


def test_remove_cap_blocked_when_pressurized():
    decision = SafetyEngine().evaluate(
        WorkerAction.REMOVE_PRESSURE_CAP,
        safe_maintenance_state(pressure_psi=78),
    )
    assert decision.status is SafetyStatus.BLOCKED
    assert any("pressurized" in hazard for hazard in decision.hazards)


def test_remove_cap_allowed_when_pressure_zero():
    decision = SafetyEngine().evaluate(
        WorkerAction.REMOVE_PRESSURE_CAP, safe_maintenance_state()
    )
    assert decision.status is SafetyStatus.SAFE
    assert decision.authorized


def test_remove_cap_requires_verified_lockout():
    decision = SafetyEngine().evaluate(
        WorkerAction.REMOVE_PRESSURE_CAP,
        MachineState(lockout_applied=True, lockout_verified=False),
    )
    assert decision.status is SafetyStatus.BLOCKED
    assert "Zero-energy lockout has not been verified" in decision.hazards


def test_machine_start_blocked_during_lockout():
    decision = SafetyEngine().evaluate(
        WorkerAction.START_MACHINE, MachineState(lockout_applied=True)
    )
    assert decision.status is SafetyStatus.BLOCKED


def test_robot_or_worker_action_blocked_during_emergency():
    decision = SafetyEngine().evaluate(
        WorkerAction.REMOVE_PRESSURE_CAP,
        safe_maintenance_state(emergency_stop=True),
    )
    assert decision.status is SafetyStatus.BLOCKED
    assert not decision.authorized


def test_critical_gas_blocks_every_action():
    decision = SafetyEngine().evaluate(
        WorkerAction.CLOSE_ISOLATION_VALVE, MachineState(gas_ppm=82)
    )
    assert decision.status is SafetyStatus.BLOCKED
    assert any("critical" in hazard for hazard in decision.hazards)


def test_unknown_intent_never_produces_action():
    assert parse_demo_phrase("do something clever with the robot") is None


def test_simulator_prevents_opening_pressurized_cap():
    simulator = IndustrialMachineSimulator(
        safe_maintenance_state(pressure_psi=78)
    )
    with pytest.raises(InvalidTransition, match="pressure"):
        simulator.apply(WorkerAction.REMOVE_PRESSURE_CAP)


def test_simulator_happy_path_to_open_housing():
    simulator = IndustrialMachineSimulator(
        MachineState(power_on=True, pressure_psi=78, isolation_valve_open=True)
    )
    for action in (
        WorkerAction.TURN_OFF_POWER,
        WorkerAction.APPLY_LOCKOUT,
        WorkerAction.CLOSE_ISOLATION_VALVE,
        WorkerAction.DEPRESSURIZE,
        WorkerAction.VERIFY_ZERO_ENERGY,
        WorkerAction.REMOVE_PRESSURE_CAP,
    ):
        simulator.apply(action)
    assert simulator.state.pressure_cap_removed
    assert simulator.state.pressure_psi == 0
