from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from clodbot.core.events import EventRecord
from clodbot.core.world_state import MachineState


@dataclass(frozen=True)
class RobotState:
    ready: bool = True
    moving: bool = False
    action: str = "SAFE_POSE"
    target: Optional[str] = None
    proximity_clear: bool = True


@dataclass(frozen=True)
class VisionState:
    worker_detected: bool = True
    detected_component: str = "filter_housing"
    visible_tools: List[str] = field(default_factory=lambda: ["13mm_wrench", "screwdriver"])
    camera_online: bool = True


@dataclass(frozen=True)
class TelemetryState:
    temperature_c: float = 42.1
    vibration_mm_s: float = 2.9
    gas_ppm: float = 18.0
    sample: int = 0


@dataclass(frozen=True)
class PredictionState:
    phase: str = "idle"
    action: Optional[str] = None
    consequence: Optional[str] = None
    hazard_radius_m: float = 0.0
    worker_exposed: bool = False
    fidelity: str = "DETERMINISTIC CONSEQUENCE MODEL"


@dataclass(frozen=True)
class CyberwaveState:
    status: str = "MOCK"
    mode: str = "simulation"
    sdk_version: Optional[str] = None
    environment_id: Optional[str] = None
    robot_twin_id: Optional[str] = None
    camera_twin_id: Optional[str] = None
    detail: str = "Local deterministic twin adapter"


@dataclass(frozen=True)
class WorldSnapshot:
    revision: int
    machine: MachineState
    robot: RobotState
    vision: VisionState
    telemetry: TelemetryState
    prediction: PredictionState
    cyberwave: CyberwaveState
    procedure: Dict[str, Any]
    safety: Dict[str, Any]
    emergency: str
    current_intent: Optional[Dict[str, Any]]
    events: List[EventRecord]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["events"] = [event.to_dict() for event in self.events]
        return data
