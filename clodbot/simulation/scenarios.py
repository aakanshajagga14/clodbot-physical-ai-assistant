from dataclasses import dataclass
from typing import Dict

from clodbot.core.enums import WorkerAction
from clodbot.core.world_state import MachineState


@dataclass(frozen=True)
class DemoScenario:
    slug: str
    title: str
    description: str
    state: MachineState
    proposed_action: WorkerAction


SCENARIOS: Dict[str, DemoScenario] = {
    "unsafe": DemoScenario(
        "unsafe", "Unsafe hydraulic maintenance",
        "A worker attempts to open a pressurized hydraulic housing.",
        MachineState(pressure_psi=78, isolation_valve_open=True, lockout_applied=True,
                     worker_in_hazard_zone=True),
        WorkerAction.REMOVE_PRESSURE_CAP,
    ),
    "correct": DemoScenario(
        "correct", "Correct maintenance procedure",
        "All zero-energy prerequisites have been satisfied and verified.",
        MachineState(pressure_psi=0, isolation_valve_open=False, lockout_applied=True,
                     lockout_verified=True),
        WorkerAction.REMOVE_PRESSURE_CAP,
    ),
    "gas": DemoScenario(
        "gas", "Gas emergency",
        "A gas excursion forces all normal activity to stop.",
        MachineState(gas_ppm=82, emergency_stop=True, worker_in_hazard_zone=True),
        WorkerAction.REMOVE_PRESSURE_CAP,
    ),
    "tool": DemoScenario(
        "tool", "Tool assistance",
        "A safe workstation is ready for guided housing removal with a 13 mm wrench.",
        MachineState(lockout_applied=True, lockout_verified=True),
        WorkerAction.REMOVE_PRESSURE_CAP,
    ),
}
