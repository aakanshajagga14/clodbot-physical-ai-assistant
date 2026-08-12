import json
from dataclasses import dataclass
from importlib import resources
from typing import List, Optional

from clodbot.core.enums import WorkerAction
from clodbot.core.world_state import MachineState


@dataclass(frozen=True)
class ProcedureStep:
    number: int
    instruction: str
    action: WorkerAction
    tool: Optional[str] = None


class ProcedureEngine:
    def __init__(self) -> None:
        path = resources.files("clodbot.procedures").joinpath("hydraulic_filter.yaml")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.name: str = data["name"]
        self.steps: List[ProcedureStep] = [
            ProcedureStep(i + 1, item["instruction"], WorkerAction(item["action"]), item.get("tool"))
            for i, item in enumerate(data["steps"])
        ]
        self.completed: List[int] = []

    @property
    def current_step(self) -> ProcedureStep:
        for step in self.steps:
            if step.number not in self.completed:
                return step
        return self.steps[-1]

    def expected_action(self) -> WorkerAction:
        return self.current_step.action

    def mark_completed(self, action: WorkerAction) -> ProcedureStep:
        step = self.current_step
        if action is not step.action:
            raise ValueError(f"unsafe skipped step: expected {step.action.value}, received {action.value}")
        self.completed.append(step.number)
        return step

    def skipped_prerequisites(self, action: WorkerAction) -> List[ProcedureStep]:
        targets = [step for step in self.steps if step.action is action]
        if not targets:
            return []
        return [step for step in self.steps if step.number < targets[0].number and step.number not in self.completed]

    def reconcile(self, state: MachineState) -> None:
        """Advance only through contiguous steps directly evidenced by machine state."""
        evidence = [
            not state.power_on,
            state.lockout_applied,
            not state.isolation_valve_open,
            state.pressure_psi <= 5,
            state.lockout_verified and state.pressure_psi <= 5,
            state.pressure_cap_removed,
            not state.filter_installed,
            state.filter_installed and state.pressure_cap_removed,
            state.filter_installed and not state.pressure_cap_removed,
            state.work_area_clear and not state.worker_in_hazard_zone,
            not state.lockout_applied,
            state.power_on,
        ]
        self.completed = []
        for step, is_complete in zip(self.steps, evidence):
            if not is_complete:
                break
            self.completed.append(step.number)
