from dataclasses import dataclass
from enum import Enum
from typing import Optional

from clodbot.core.world import RobotState, VisionState
from clodbot.core.world_state import MachineState


class RobotAction(str, Enum):
    POINT_TO_TOOL = "POINT_TO_TOOL"
    MOVE_TO_SAFE_POSE = "MOVE_TO_SAFE_POSE"


@dataclass(frozen=True)
class RobotActionRequest:
    action: RobotAction
    target: Optional[str]
    confidence: float


@dataclass(frozen=True)
class RobotDecision:
    allowed: bool
    reason: str


class RobotSafetyGate:
    MIN_CONFIDENCE = 0.85

    def validate(
        self, request: RobotActionRequest, machine: MachineState,
        robot: RobotState, vision: VisionState,
    ) -> RobotDecision:
        if machine.emergency_stop or machine.gas_ppm >= 50:
            return RobotDecision(False, "Emergency condition blocks robot motion")
        if not robot.ready:
            return RobotDecision(False, "Robot is not ready")
        if not robot.proximity_clear or machine.worker_in_hazard_zone:
            return RobotDecision(False, "Worker proximity is not clear")
        if request.confidence < self.MIN_CONFIDENCE:
            return RobotDecision(False, "Action confidence is below threshold")
        if not request.target or request.target not in vision.visible_tools:
            return RobotDecision(False, "Robot target is unknown or not visible")
        return RobotDecision(True, "Semantic action and target validated")
