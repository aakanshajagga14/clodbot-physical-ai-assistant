from dataclasses import dataclass
from enum import Enum
import asyncio
import importlib.metadata
import os
from typing import Any, Dict, Optional

from clodbot.core.world import CyberwaveState, RobotState
from clodbot.robotics import RobotAction


class CyberwaveMode(str, Enum):
    SIMULATION = "simulation"
    LIVE = "live"


@dataclass(frozen=True)
class CyberwaveConfig:
    mode: CyberwaveMode = CyberwaveMode.SIMULATION
    mock: bool = True
    runtime: str = "playground"

    @classmethod
    def from_environment(cls) -> "CyberwaveConfig":
        raw = os.getenv("CLODBOT_MODE", CyberwaveMode.SIMULATION.value)
        mock = os.getenv("CLODBOT_CYBERWAVE_MOCK", "true").lower() not in {"0", "false", "no"}
        return cls(CyberwaveMode(raw), mock, os.getenv("CLODBOT_CYBERWAVE_RUNTIME", "playground"))

    def require_live_opt_in(self) -> None:
        if self.mode is CyberwaveMode.LIVE and os.getenv("CLODBOT_ALLOW_LIVE") != "I_UNDERSTAND":
            raise RuntimeError("live mode requires CLODBOT_ALLOW_LIVE=I_UNDERSTAND")


class MockCyberwaveWorld:
    def __init__(self, config: Optional[CyberwaveConfig] = None) -> None:
        self.config = config or CyberwaveConfig()
        self.connected = False
        self.robot = RobotState()
        self.events = []

    async def connect(self) -> CyberwaveState:
        self.connected = True
        return self.state

    async def disconnect(self) -> None:
        self.connected = False

    async def setup_environment(self) -> CyberwaveState:
        return self.state

    async def get_robot_state(self) -> RobotState:
        return self.robot

    async def read_camera(self) -> Optional[bytes]:
        return None

    async def execute_robot_action(self, action: RobotAction, target: str) -> RobotState:
        self.robot = RobotState(ready=True, moving=True, action=action.value, target=target)
        await asyncio.sleep(0.25)
        self.robot = RobotState(ready=True, moving=False, action=action.value, target=target)
        return self.robot

    async def publish_event(self, event: Dict[str, Any]) -> None:
        self.events.append(event)

    async def set_mode(self, mode: CyberwaveMode) -> CyberwaveState:
        self.config = CyberwaveConfig(mode, True, self.config.runtime)
        return self.state

    @property
    def state(self) -> CyberwaveState:
        return CyberwaveState(
            status="MOCK", mode=self.config.mode.value,
            detail="Cyberwave unavailable or mock explicitly enabled",
            robot_twin_id="local-so101-preview", camera_twin_id=None,
            environment_id="mock-hydraulic-station",
        )


class CyberwaveWorld:
    """Single owner of verified Cyberwave SDK 0.6.4 calls."""

    POINT_POSE = {"_1": 0.42, "_2": -0.18, "_3": 0.56, "_4": 0.12, "_5": 0.0, "_6": 0.0}
    SAFE_POSE = {"_1": 0.0, "_2": -0.35, "_3": 0.7, "_4": 0.0, "_5": 0.0, "_6": 0.0}

    def __init__(self, config: Optional[CyberwaveConfig] = None) -> None:
        self.config = config or CyberwaveConfig.from_environment()
        self.config.require_live_opt_in()
        self._client: Any = None
        self._robot: Any = None
        self._camera: Any = None
        self._robot_state = RobotState(ready=False)
        self._detail = f"Cyberwave {self.config.runtime} runtime"

    async def connect(self) -> CyberwaveState:
        from cyberwave import Cyberwave  # type: ignore[import-not-found]

        self._client = await asyncio.to_thread(Cyberwave)
        runtime = "live" if self.config.mode is CyberwaveMode.LIVE else self.config.runtime
        await asyncio.to_thread(self._client.affect, runtime)
        return self.state

    async def setup_environment(self) -> CyberwaveState:
        if self._client is None:
            raise RuntimeError("Cyberwave client is not connected")
        env_id = os.getenv("CYBERWAVE_ENVIRONMENT_ID")
        robot_id = os.getenv("CYBERWAVE_TWIN_ID")
        camera_id = os.getenv("CYBERWAVE_CAMERA_TWIN_ID")
        if not env_id or not robot_id:
            raise RuntimeError("real Cyberwave mode requires existing environment and robot twin IDs")
        # Cyberwave's environment-scoped twin listing is the authoritative lookup
        # for workspace twins. Some deployments do not expose the global
        # /twins/{uuid} route used by the compact client.twin(twin_id=...) helper.
        try:
            twins = await asyncio.to_thread(self._client.twins.list, environment_id=env_id)
        except Exception:
            # Some Cyberwave deployments authorize the environment and global
            # twin collection but reject the environment-scoped twins route.
            # Fall back to the SDK's global read and filter locally.
            visible_twins = await asyncio.to_thread(self._client.twins.list)
            twins = [
                item for item in visible_twins
                if str(getattr(item, "environment_uuid", "")) == env_id
            ]
        robot_data = next((item for item in twins if str(getattr(item, "uuid", "")) == robot_id), None)
        if robot_data is None:
            raise RuntimeError("configured SO-101 twin is not present in the Cyberwave environment")
        from cyberwave.twin import create_twin  # type: ignore[import-not-found]

        self._robot = create_twin(self._client, robot_data, registry_id="the-robot-studio/so101")
        if camera_id:
            camera_data = next((item for item in twins if str(getattr(item, "uuid", "")) == camera_id), None)
            if camera_data is not None:
                self._camera = create_twin(self._client, camera_data, registry_id="cyberwave/standard-cam")
        self._robot_state = RobotState(ready=True)
        return self.state

    async def disconnect(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.disconnect)

    async def read_camera(self) -> Optional[bytes]:
        if self._camera is None:
            return None
        return await asyncio.to_thread(self._camera.capture_frame, "bytes")

    async def get_robot_state(self) -> RobotState:
        return self._robot_state

    async def execute_robot_action(self, action: RobotAction, target: str) -> RobotState:
        if self._robot is None:
            raise RuntimeError("robot twin is unavailable")
        pose = self.POINT_POSE if action is RobotAction.POINT_TO_TOOL else self.SAFE_POSE
        self._robot_state = RobotState(True, True, action.value, target)
        try:
            # Playground is a connected, non-billable preview runtime. It does not
            # attach a teleoperation policy, so remote joint commands are deliberately
            # not sent. The local digital twin still performs the validated preview.
            if self.config.mode is CyberwaveMode.SIMULATION and self.config.runtime == "playground":
                self._detail = "Cyberwave playground connected · local motion preview"
                await asyncio.sleep(0.65)
            else:
                await asyncio.to_thread(self._robot.set_joints, pose)
                self._detail = f"Cyberwave {self.config.runtime} runtime"
        except Exception as exc:
            self._detail = "Cyberwave connected · motion policy unavailable"
            raise RuntimeError("Cyberwave motion command was rejected; verify the controller policy") from exc
        finally:
            self._robot_state = RobotState(True, False, action.value, target)
        return self._robot_state

    async def publish_event(self, event: Dict[str, Any]) -> None:
        if self._client is None or self._robot is None:
            return
        if self.config.mode is CyberwaveMode.SIMULATION and self.config.runtime == "playground":
            return
        if event.get("severity") == "critical":
            await asyncio.to_thread(
                self._client.publish_alert, self._robot.uuid, event["title"],
                description=event.get("detail", ""), severity="critical",
                alert_type=event.get("kind", "clodbot_event"), source_type="simulation",
            )

    async def set_mode(self, mode: CyberwaveMode) -> CyberwaveState:
        self.config = CyberwaveConfig(mode, False, self.config.runtime)
        self.config.require_live_opt_in()
        runtime = "live" if mode is CyberwaveMode.LIVE else self.config.runtime
        await asyncio.to_thread(self._client.affect, runtime)
        return self.state

    @property
    def state(self) -> CyberwaveState:
        return CyberwaveState(
            status="CONNECTED", mode=self.config.mode.value,
            sdk_version=importlib.metadata.version("cyberwave"),
            environment_id=os.getenv("CYBERWAVE_ENVIRONMENT_ID"),
            robot_twin_id=os.getenv("CYBERWAVE_TWIN_ID"),
            camera_twin_id=os.getenv("CYBERWAVE_CAMERA_TWIN_ID"),
            detail=self._detail,
        )


async def create_cyberwave_world(config: Optional[CyberwaveConfig] = None):
    selected = config or CyberwaveConfig.from_environment()
    if selected.mock:
        world = MockCyberwaveWorld(selected)
        await world.connect()
        return world
    try:
        world = CyberwaveWorld(selected)
        await world.connect()
        await world.setup_environment()
        return world
    except Exception:
        fallback = MockCyberwaveWorld(CyberwaveConfig(selected.mode, True, selected.runtime))
        await fallback.connect()
        return fallback
