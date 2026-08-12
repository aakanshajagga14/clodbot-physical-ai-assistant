from clodbot.core.enums import WorkerAction
from clodbot.core.world_state import MachineState


class InvalidTransition(RuntimeError):
    pass


class IndustrialMachineSimulator:
    """Stateful simulator with physical invariants independent of the safety UI."""

    def __init__(self, initial_state: MachineState = MachineState()) -> None:
        self._state = initial_state

    @property
    def state(self) -> MachineState:
        return self._state

    def reset(self, state: MachineState) -> MachineState:
        self._state = state
        return self._state

    def apply(self, action: WorkerAction) -> MachineState:
        s = self._state
        changes = {}

        if action is WorkerAction.TURN_OFF_POWER:
            changes = {"power_on": False}
        elif action is WorkerAction.OPEN_ISOLATION_VALVE:
            self._require(not s.pressure_cap_removed, "cannot open the valve with the housing open")
            changes = {"isolation_valve_open": True}
        elif action is WorkerAction.CLOSE_ISOLATION_VALVE:
            changes = {"isolation_valve_open": False}
        elif action is WorkerAction.DEPRESSURIZE:
            self._require(not s.power_on, "turn off power before depressurizing")
            self._require(not s.isolation_valve_open, "close isolation valve B before depressurizing")
            changes = {"pressure_psi": 0.0, "lockout_verified": False}
        elif action is WorkerAction.APPLY_LOCKOUT:
            self._require(not s.power_on, "turn off power before applying lockout")
            changes = {"lockout_applied": True, "lockout_verified": False}
        elif action is WorkerAction.VERIFY_ZERO_ENERGY:
            self._require(s.lockout_applied, "apply lockout before verification")
            self._require(s.pressure_psi <= 5, "pressure must be at or below 5 PSI")
            changes = {"lockout_verified": True}
        elif action is WorkerAction.REMOVE_PRESSURE_CAP:
            self._require_safe_open(s)
            changes = {"pressure_cap_removed": True}
        elif action is WorkerAction.REMOVE_FILTER:
            self._require(s.pressure_cap_removed, "open the housing before removing the filter")
            self._require(s.filter_installed, "filter is already removed")
            changes = {"filter_installed": False}
        elif action is WorkerAction.INSTALL_FILTER:
            self._require(s.pressure_cap_removed, "open the housing before installing the filter")
            self._require(not s.filter_installed, "filter is already installed")
            changes = {"filter_installed": True}
        elif action is WorkerAction.INSTALL_PRESSURE_CAP:
            self._require(s.pressure_cap_removed, "pressure cap is already installed")
            self._require(s.filter_installed, "install the filter before closing the housing")
            changes = {"pressure_cap_removed": False}
        elif action is WorkerAction.VERIFY_WORK_AREA_CLEAR:
            self._require(not s.worker_in_hazard_zone, "worker remains in the hazard zone")
            changes = {"work_area_clear": True}
        elif action is WorkerAction.REMOVE_LOCKOUT:
            self._require(not s.pressure_cap_removed, "reassemble the housing first")
            self._require(s.filter_installed, "install the filter first")
            self._require(s.work_area_clear, "clear the work area first")
            changes = {"lockout_applied": False, "lockout_verified": False}
        elif action is WorkerAction.START_MACHINE:
            self._require(not s.lockout_applied, "cannot start while lockout is applied")
            self._require(not s.pressure_cap_removed, "cannot start with housing open")
            self._require(s.filter_installed, "cannot start without a filter")
            self._require(not s.worker_in_hazard_zone, "worker is in the hazard zone")
            self._require(not s.emergency_stop and s.gas_ppm < 50, "emergency condition is active")
            changes = {"power_on": True, "isolation_valve_open": True, "pressure_psi": 78.0}
        else:  # pragma: no cover - enum exhaustiveness guard
            raise InvalidTransition(f"unsupported action: {action}")

        self._state = s.evolve(**changes)
        return self._state

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise InvalidTransition(message)

    def _require_safe_open(self, state: MachineState) -> None:
        self._require(not state.power_on, "machine power must be off")
        self._require(not state.isolation_valve_open, "isolation valve B must be closed")
        self._require(state.pressure_psi <= 5, "pressure must be at or below 5 PSI")
        self._require(state.lockout_verified, "zero-energy lockout must be verified")
        self._require(not state.pressure_cap_removed, "pressure cap is already removed")
