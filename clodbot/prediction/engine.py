from clodbot.core.enums import WorkerAction
from clodbot.core.world import PredictionState
from clodbot.core.world_state import MachineState


class ConsequenceEngine:
    """Deterministic what-if model; explicitly not a physics simulation."""

    def predict(self, action: WorkerAction, state: MachineState) -> PredictionState:
        if action is WorkerAction.REMOVE_PRESSURE_CAP and state.pressure_psi > 5:
            radius = min(2.5, 0.65 + state.pressure_psi / 90.0)
            return PredictionState(
                phase="complete",
                action=action.value,
                consequence="PRESSURIZED_HYDRAULIC_RELEASE",
                hazard_radius_m=round(radius, 1),
                worker_exposed=state.worker_in_hazard_zone,
            )
        if action is WorkerAction.START_MACHINE and state.worker_in_hazard_zone:
            return PredictionState(
                phase="complete", action=action.value, consequence="WORKER_STRIKE_EXPOSURE",
                hazard_radius_m=1.2, worker_exposed=True,
            )
        return PredictionState(
            phase="complete", action=action.value, consequence="NO_HAZARDOUS_CONSEQUENCE_PREDICTED",
            hazard_radius_m=0.0, worker_exposed=False,
        )
