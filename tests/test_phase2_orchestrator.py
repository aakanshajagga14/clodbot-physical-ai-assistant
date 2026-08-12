import asyncio

import pytest

from clodbot.core.enums import SafetyStatus, WorkerAction
from clodbot.core.world_state import MachineState
from clodbot.cyberwave import CyberwaveConfig, CyberwaveMode, CyberwaveWorld, MockCyberwaveWorld
from clodbot.orchestrator import ClodbotOrchestrator
from clodbot.prediction import ConsequenceEngine
from clodbot.robotics import RobotAction, RobotActionRequest, RobotSafetyGate
from clodbot.simulation import InvalidTransition


def run(coro):
    return asyncio.run(coro)


def test_world_state_updates_from_simulator():
    async def exercise():
        mock = MockCyberwaveWorld()
        await mock.connect()
        orchestrator = ClodbotOrchestrator(mock)
        before = await orchestrator.snapshot()
        after = await orchestrator.perform_machine_action(WorkerAction.CLOSE_ISOLATION_VALVE)
        assert before.machine.isolation_valve_open
        assert not after.machine.isolation_valve_open
        assert after.revision > before.revision

    run(exercise())


def test_cyberwave_mock_adapter():
    async def exercise():
        mock = MockCyberwaveWorld(CyberwaveConfig())
        state = await mock.connect()
        assert state.status == "MOCK"
        assert state.robot_twin_id == "local-so101-preview"
        assert state.camera_twin_id is None
        assert (await mock.get_robot_state()).ready

    run(exercise())


def test_cyberwave_playground_robot_action_completes_as_local_preview():
    async def exercise():
        world = CyberwaveWorld(CyberwaveConfig(CyberwaveMode.SIMULATION, False, "playground"))
        world._robot = object()
        result = await world.execute_robot_action(RobotAction.POINT_TO_TOOL, "13mm_wrench")
        assert result.ready
        assert not result.moving
        assert result.action == RobotAction.POINT_TO_TOOL.value
        assert "local motion preview" in world._detail

    run(exercise())


def test_cyberwave_robot_failure_never_leaves_moving_state():
    class RejectingRobot:
        def set_joints(self, pose):
            raise RuntimeError("sensitive vendor failure")

    async def exercise():
        world = CyberwaveWorld(CyberwaveConfig(CyberwaveMode.SIMULATION, False, "simulation"))
        world._robot = RejectingRobot()
        with pytest.raises(RuntimeError, match="controller policy"):
            await world.execute_robot_action(RobotAction.POINT_TO_TOOL, "13mm_wrench")
        assert not world._robot_state.moving

    run(exercise())


def test_prediction_blocked_for_pressurized_cap():
    state = MachineState(
        pressure_psi=78, isolation_valve_open=True, lockout_applied=True,
        worker_in_hazard_zone=True,
    )
    prediction = ConsequenceEngine().predict(WorkerAction.REMOVE_PRESSURE_CAP, state)
    assert prediction.consequence == "PRESSURIZED_HYDRAULIC_RELEASE"
    assert prediction.worker_exposed


def test_prediction_safe_after_depressurization():
    async def exercise():
        mock = MockCyberwaveWorld()
        await mock.connect()
        orchestrator = ClodbotOrchestrator(mock)
        orchestrator.PRESSURE_SEQUENCE = (3.0, 0.0)
        await orchestrator.perform_machine_action(WorkerAction.CLOSE_ISOLATION_VALVE)
        await orchestrator.perform_machine_action(WorkerAction.DEPRESSURIZE)
        await asyncio.sleep(1.1)
        snapshot = await orchestrator.evaluate_intent("Can I remove the pressure cap?")
        assert snapshot.machine.pressure_psi == 0
        assert snapshot.safety["status"] == SafetyStatus.SAFE.value
        assert snapshot.prediction.consequence == "NO_HAZARDOUS_CONSEQUENCE_PREDICTED"

    run(exercise())


def test_emergency_blocks_robot_action():
    gate = RobotSafetyGate()
    decision = gate.validate(
        RobotActionRequest(RobotAction.POINT_TO_TOOL, "13mm_wrench", 0.99),
        MachineState(emergency_stop=True),
        MockCyberwaveWorld().robot,
        ClodbotOrchestrator(MockCyberwaveWorld()).vision,
    )
    assert not decision.allowed
    assert "Emergency" in decision.reason


def test_robot_action_requires_valid_target():
    gate = RobotSafetyGate()
    decision = gate.validate(
        RobotActionRequest(RobotAction.POINT_TO_TOOL, "imaginary_tool", 0.99),
        MachineState(),
        MockCyberwaveWorld().robot,
        ClodbotOrchestrator(MockCyberwaveWorld()).vision,
    )
    assert not decision.allowed
    assert "target" in decision.reason.lower()


def test_scenario_reset_restores_initial_state():
    async def exercise():
        mock = MockCyberwaveWorld()
        await mock.connect()
        orchestrator = ClodbotOrchestrator(mock)
        await orchestrator.load_scenario("correct")
        reset = await orchestrator.reset()
        assert reset.machine.pressure_psi == 78
        assert reset.machine.isolation_valve_open
        assert reset.machine.lockout_applied
        assert reset.machine.worker_in_hazard_zone

    run(exercise())


def test_orchestrator_rejects_robot_motion_near_worker():
    async def exercise():
        mock = MockCyberwaveWorld()
        await mock.connect()
        orchestrator = ClodbotOrchestrator(mock)
        with pytest.raises(InvalidTransition, match="proximity"):
            await orchestrator.point_to_tool()

    run(exercise())
