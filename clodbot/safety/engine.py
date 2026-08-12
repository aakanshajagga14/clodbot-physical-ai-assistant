import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, List, Mapping, Optional

from clodbot.core.enums import SafetyStatus, WorkerAction
from clodbot.core.world_state import MachineState


@dataclass(frozen=True)
class CheckResult:
    field: str
    passed: bool
    actual: Any
    hazard: str


@dataclass(frozen=True)
class SafetyDecision:
    action: WorkerAction
    status: SafetyStatus
    hazards: List[str]
    required_actions: List[str]
    checks: List[CheckResult]

    @property
    def authorized(self) -> bool:
        return self.status is SafetyStatus.SAFE


class SafetyEngine:
    """Deterministic authorization boundary; no model output can bypass it."""

    def __init__(self, rules: Optional[Mapping[str, Any]] = None) -> None:
        self._rules = dict(rules) if rules is not None else self._load_rules()

    @staticmethod
    def _load_rules() -> Dict[str, Any]:
        # JSON is a strict subset of YAML, allowing a .yaml config with no runtime parser.
        rule_file = resources.files("clodbot.safety.rules").joinpath("hydraulic.yaml")
        return json.loads(rule_file.read_text(encoding="utf-8"))

    def evaluate(self, action: WorkerAction, state: MachineState) -> SafetyDecision:
        hazards: List[str] = []
        required: List[str] = []
        checks: List[CheckResult] = []

        if state.emergency_stop:
            hazards.append("Software emergency stop is active")
            required.append("Resolve the emergency and reset the emergency stop")
        if state.gas_ppm >= float(self._rules["global"]["critical_gas_ppm"]):
            hazards.append(f"Gas concentration is critical at {state.gas_ppm:.1f} ppm")
            required.append("Evacuate the hazard zone and investigate remotely")

        rule = self._rules.get("actions", {}).get(action.value, {})
        for field, condition in rule.get("requirements", {}).items():
            actual = getattr(state, field)
            passed = self._matches(actual, condition)
            checks.append(
                CheckResult(
                    field=field,
                    passed=passed,
                    actual=actual,
                    hazard=condition["hazard"],
                )
            )
            if not passed:
                hazards.append(condition["hazard"])
                required.append(condition["required_action"])

        if hazards:
            status = SafetyStatus.BLOCKED
        elif state.worker_in_hazard_zone and action in {
            WorkerAction.OPEN_ISOLATION_VALVE,
            WorkerAction.START_MACHINE,
        }:
            status = SafetyStatus.CAUTION
            hazards.append("Worker is inside the machine hazard zone")
            required.append("Ask the worker to leave the hazard zone")
        else:
            status = SafetyStatus.SAFE

        return SafetyDecision(action, status, hazards, list(dict.fromkeys(required)), checks)

    @staticmethod
    def _matches(actual: Any, condition: Mapping[str, Any]) -> bool:
        tests = []
        if "equals" in condition:
            tests.append(actual == condition["equals"])
        if "max" in condition:
            tests.append(float(actual) <= float(condition["max"]))
        if "min" in condition:
            tests.append(float(actual) >= float(condition["min"]))
        if not tests:
            raise ValueError("rule condition requires equals, min, or max")
        return all(tests)
