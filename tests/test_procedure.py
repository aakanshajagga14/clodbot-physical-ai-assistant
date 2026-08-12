import pytest

from clodbot.core.enums import WorkerAction
from clodbot.core.world_state import MachineState
from clodbot.procedures import ProcedureEngine
from clodbot.simulation.scenarios import SCENARIOS


def test_four_demo_scenarios_are_available():
    assert set(SCENARIOS) == {"unsafe", "correct", "gas", "tool"}


def test_procedure_has_twelve_ordered_steps():
    procedure = ProcedureEngine()
    assert len(procedure.steps) == 12
    assert procedure.expected_action() is WorkerAction.TURN_OFF_POWER


def test_procedure_rejects_skipped_step():
    procedure = ProcedureEngine()
    with pytest.raises(ValueError, match="unsafe skipped step"):
        procedure.mark_completed(WorkerAction.REMOVE_PRESSURE_CAP)
    skipped = procedure.skipped_prerequisites(WorkerAction.REMOVE_PRESSURE_CAP)
    assert len(skipped) == 5


def test_procedure_reconciles_to_first_unproven_step():
    procedure = ProcedureEngine()
    procedure.reconcile(
        MachineState(pressure_psi=78, isolation_valve_open=True, lockout_applied=True)
    )
    assert procedure.current_step.action is WorkerAction.CLOSE_ISOLATION_VALVE


def test_safe_zero_energy_state_reconciles_to_cap_removal():
    procedure = ProcedureEngine()
    procedure.reconcile(MachineState(lockout_applied=True, lockout_verified=True))
    assert procedure.current_step.action is WorkerAction.REMOVE_PRESSURE_CAP
