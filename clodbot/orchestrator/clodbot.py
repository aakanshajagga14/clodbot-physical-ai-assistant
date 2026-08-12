import asyncio
from dataclasses import asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

from clodbot.core.enums import EmergencyLevel, SafetyStatus, WorkerAction
from clodbot.core.events import EventRecord
from clodbot.core.world import PredictionState, TelemetryState, VisionState, WorldSnapshot
from clodbot.cyberwave import create_cyberwave_world
from clodbot.intent import RuleIntentProvider
from clodbot.prediction import ConsequenceEngine
from clodbot.procedures import ProcedureEngine
from clodbot.robotics import RobotAction, RobotActionRequest, RobotSafetyGate
from clodbot.safety import SafetyEngine
from clodbot.simulation import IndustrialMachineSimulator, InvalidTransition
from clodbot.simulation.scenarios import SCENARIOS


Subscriber = Callable[[Dict[str, Any]], Awaitable[None]]


class ClodbotOrchestrator:
    TICK_SECONDS = 0.5
    PRESSURE_SEQUENCE = (78.0, 67.0, 51.0, 32.0, 17.0, 7.0, 3.0, 0.0)

    def __init__(self, cyberwave_world: Any = None) -> None:
        self.simulator = IndustrialMachineSimulator(SCENARIOS["unsafe"].state)
        self.safety_engine = SafetyEngine()
        self.procedure = ProcedureEngine()
        self.intent_provider = RuleIntentProvider()
        self.consequence_engine = ConsequenceEngine()
        self.robot_gate = RobotSafetyGate()
        self.cyberwave = cyberwave_world
        self.vision = VisionState()
        self.telemetry = TelemetryState(gas_ppm=self.simulator.state.gas_ppm)
        self.prediction = PredictionState()
        self.current_intent: Optional[Dict[str, Any]] = None
        self.events: List[EventRecord] = []
        self.revision = 0
        self._sequence = 0
        self._subscribers: List[Subscriber] = []
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._pressure_task: Optional[asyncio.Task] = None
        self._lock: Optional[asyncio.Lock] = None
        self._log("system", "Hydraulic station initialized", "Flagship unsafe scenario loaded")

    async def start(self) -> None:
        if self.cyberwave is None:
            self.cyberwave = await create_cyberwave_world()
        self._running = True
        self._loop_task = asyncio.create_task(self._event_loop())
        await self._publish()

    @property
    def _state_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def stop(self) -> None:
        self._running = False
        for task in (self._pressure_task, self._loop_task):
            if task and not task.done():
                task.cancel()
        if self.cyberwave is not None:
            await self.cyberwave.disconnect()

    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _event_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self.TICK_SECONDS)
                async with self._state_lock:
                    sample = self.telemetry.sample + 1
                    machine = self.simulator.state
                    target_temp = 48.0 if machine.power_on else 42.0
                    temperature = self.telemetry.temperature_c + (target_temp - self.telemetry.temperature_c) * 0.08
                    vibration = 2.9 if machine.power_on else 0.35
                    self.telemetry = TelemetryState(
                        round(temperature, 1), vibration, machine.gas_ppm, sample
                    )
                    if self.cyberwave:
                        robot = await self.cyberwave.get_robot_state()
                        self.vision = VisionState(
                            worker_detected=True,
                            detected_component=self.vision.detected_component,
                            visible_tools=self.vision.visible_tools,
                            camera_online=self.vision.camera_online,
                        )
                    self.revision += 1
                await self._publish()
        except asyncio.CancelledError:
            pass

    async def snapshot(self) -> WorldSnapshot:
        machine = self.simulator.state
        self.procedure.reconcile(machine)
        action = WorkerAction.REMOVE_PRESSURE_CAP
        decision = self.safety_engine.evaluate(action, machine)
        robot = await self.cyberwave.get_robot_state() if self.cyberwave else None
        checks = [
            {"field": item.field, "passed": item.passed, "actual": item.actual, "hazard": item.hazard}
            for item in decision.checks
        ]
        procedure = {
            "name": self.procedure.name,
            "current_step": self.procedure.current_step.number,
            "steps": [
                {
                    "number": step.number, "instruction": step.instruction,
                    "action": step.action.value,
                    "status": "complete" if step.number in self.procedure.completed
                    else "current" if step.number == self.procedure.current_step.number else "pending",
                    "tool": step.tool,
                }
                for step in self.procedure.steps
            ],
        }
        emergency = (
            EmergencyLevel.CRITICAL.value if machine.emergency_stop or machine.gas_ppm >= 50
            else EmergencyLevel.CAUTION.value if machine.worker_in_hazard_zone and machine.pressure_psi > 5
            else EmergencyLevel.NORMAL.value
        )
        safety = {
            "action": action.value, "status": decision.status.value,
            "authorized": decision.authorized, "hazards": decision.hazards,
            "required_actions": decision.required_actions, "checks": checks,
        }
        return WorldSnapshot(
            self.revision, machine, robot, self.vision, self.telemetry, self.prediction,
            self.cyberwave.state, procedure, safety, emergency, self.current_intent,
            list(reversed(self.events[-40:])),
        )

    async def evaluate_intent(self, text: str) -> WorldSnapshot:
        result = self.intent_provider.parse(text)
        self.current_intent = {
            "text": text, "action": result.action.value if result.action else None,
            "confidence": result.confidence, "category": result.category,
            "tool_query": result.tool_query,
        }
        self._log("intent", "Worker intent detected", result.action.value if result.action else result.category)
        if result.category == "tool_query":
            self.prediction = PredictionState(
                phase="complete", consequence="TOOL_IDENTIFIED_13MM_WRENCH"
            )
            self._log("guidance", "Required tool identified", "13 mm wrench")
            await self._publish()
            return await self.snapshot()
        if result.action is None or result.confidence < 0.85:
            self.prediction = PredictionState(phase="uncertain")
            self._log("intent", "Intent needs clarification", "No physical action authorized", "warning")
            await self._publish()
            return await self.snapshot()

        self.prediction = PredictionState(phase="analyzing", action=result.action.value)
        self._log("prediction", "Predictive safety simulation started", result.action.value)
        await self._publish()
        await asyncio.sleep(0.35)
        self.prediction = PredictionState(phase="simulating", action=result.action.value)
        await self._publish()
        await asyncio.sleep(0.35)
        self.prediction = self.consequence_engine.predict(result.action, self.simulator.state)
        decision = self.safety_engine.evaluate(result.action, self.simulator.state)
        if self.prediction.consequence and "RELEASE" in self.prediction.consequence:
            self._log("hazard", "Hazard predicted", self.prediction.consequence, "critical")
        self._log(
            "decision", f"Action {decision.status.value.lower()}", result.action.value,
            "critical" if decision.status is SafetyStatus.BLOCKED else "info",
        )
        await self._publish()
        return await self.snapshot()

    async def perform_machine_action(self, action: WorkerAction) -> WorldSnapshot:
        async with self._state_lock:
            decision = self.safety_engine.evaluate(action, self.simulator.state)
            if decision.status is SafetyStatus.BLOCKED:
                self._log("decision", "Machine action blocked", "; ".join(decision.hazards), "warning")
                raise InvalidTransition("; ".join(decision.hazards))
            if action is WorkerAction.DEPRESSURIZE:
                if self._pressure_task and not self._pressure_task.done():
                    return await self.snapshot()
                self._pressure_task = asyncio.create_task(self._depressurize())
                self._log("machine", "Depressurization started", "Controlled pressure bleed-down")
            else:
                before = self.simulator.state
                self.simulator.apply(action)
                if action is WorkerAction.CLOSE_ISOLATION_VALVE:
                    self._log("machine", "Isolation valve B closed", "OPEN → CLOSED")
                elif action is WorkerAction.OPEN_ISOLATION_VALVE:
                    self._log("machine", "Isolation valve B opened", "CLOSED → OPEN")
                else:
                    self._log("machine", action.value.replace("_", " ").title(), "State transition accepted")
                if before != self.simulator.state:
                    self.revision += 1
        await self._publish()
        return await self.snapshot()

    async def _depressurize(self) -> None:
        try:
            current = self.simulator.state.pressure_psi
            values = [value for value in self.PRESSURE_SEQUENCE if value < current]
            if not values or values[-1] != 0:
                values.append(0.0)
            for pressure in values:
                await asyncio.sleep(0.48)
                async with self._state_lock:
                    verified = pressure < 5 and self.simulator.state.lockout_applied
                    self.simulator.reset(
                        self.simulator.state.evolve(
                            pressure_psi=pressure, lockout_verified=verified
                        )
                    )
                    self.revision += 1
                    if verified and not any(e.kind == "verification" for e in self.events[-3:]):
                        self._log("verification", "Zero-energy state verified", f"Pressure {pressure:g} PSI")
                await self._publish()
            self._log("machine", "Depressurization complete", "Pressure 0 PSI")
            await self._publish()
        except asyncio.CancelledError:
            pass

    async def load_scenario(self, slug: str) -> WorldSnapshot:
        if slug not in SCENARIOS:
            raise KeyError(slug)
        if self._pressure_task and not self._pressure_task.done():
            self._pressure_task.cancel()
        async with self._state_lock:
            self.simulator.reset(SCENARIOS[slug].state)
            self.prediction = PredictionState()
            self.current_intent = None
            self.telemetry = TelemetryState(gas_ppm=self.simulator.state.gas_ppm)
            self.revision += 1
            self._log("scenario", f"Scenario loaded: {SCENARIOS[slug].title}", SCENARIOS[slug].description)
        if slug == "gas":
            await self._critical_event()
        await self._publish()
        return await self.snapshot()

    async def reset(self) -> WorldSnapshot:
        return await self.load_scenario("unsafe")

    async def trigger_gas(self) -> WorldSnapshot:
        async with self._state_lock:
            self.simulator.reset(
                self.simulator.state.evolve(gas_ppm=82, emergency_stop=True)
            )
            self.telemetry = TelemetryState(
                self.telemetry.temperature_c, self.telemetry.vibration_mm_s, 82, self.telemetry.sample
            )
            self.revision += 1
        await self._critical_event()
        await self._publish()
        return await self.snapshot()

    async def reset_emergency(self) -> WorldSnapshot:
        async with self._state_lock:
            self.simulator.reset(
                self.simulator.state.evolve(gas_ppm=18, emergency_stop=False)
            )
            self.revision += 1
            self._log("emergency", "Emergency reset", "Gas concentration returned to nominal")
        await self._publish()
        return await self.snapshot()

    async def set_worker_zone(self, inside: bool) -> WorldSnapshot:
        async with self._state_lock:
            self.simulator.reset(self.simulator.state.evolve(worker_in_hazard_zone=inside))
            self.revision += 1
            self._log("worker", "Worker entered hazard zone" if inside else "Worker exited hazard zone")
        await self._publish()
        return await self.snapshot()

    async def point_to_tool(self, target: str = "13mm_wrench", confidence: float = 0.99) -> WorldSnapshot:
        robot = await self.cyberwave.get_robot_state()
        request = RobotActionRequest(RobotAction.POINT_TO_TOOL, target, confidence)
        decision = self.robot_gate.validate(request, self.simulator.state, robot, self.vision)
        if not decision.allowed:
            self._log("robot", "Robot motion blocked", decision.reason, "warning")
            await self._publish()
            raise InvalidTransition(decision.reason)
        self._log("robot", "Robot action authorized", f"POINT_TO_TOOL → {target}")
        await self._publish()
        await self.cyberwave.execute_robot_action(request.action, target)
        self._log("robot", "Robot pointing complete", target)
        await self._publish()
        return await self.snapshot()

    async def _critical_event(self) -> None:
        self._log("emergency", "CRITICAL SAFETY EVENT", "Gas 82 ppm // EVACUATE", "critical")
        robot = await self.cyberwave.get_robot_state()
        if robot.moving:
            await self.cyberwave.execute_robot_action(RobotAction.MOVE_TO_SAFE_POSE, "safe_pose")
        await self.cyberwave.publish_event(self.events[-1].to_dict())

    def _log(self, kind: str, title: str, detail: str = "", severity: str = "info") -> None:
        self._sequence += 1
        self.events.append(EventRecord.create(self._sequence, kind, title, detail, severity))

    async def _publish(self) -> None:
        if not self._subscribers:
            return
        payload = (await self.snapshot()).to_dict()
        stale = []
        for callback in self._subscribers:
            try:
                await callback(payload)
            except Exception:
                stale.append(callback)
        for callback in stale:
            self.unsubscribe(callback)
