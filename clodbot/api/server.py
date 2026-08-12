from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clodbot.core.enums import WorkerAction
from clodbot.orchestrator import ClodbotOrchestrator
from clodbot.simulation import InvalidTransition


orchestrator = ClodbotOrchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await orchestrator.start()
    yield
    await orchestrator.stop()


app = FastAPI(title="Clodbot Digital Twin API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IntentRequest(BaseModel):
    text: str


class ActionRequest(BaseModel):
    action: WorkerAction


class ZoneRequest(BaseModel):
    inside: bool


class RobotRequest(BaseModel):
    target: str = "13mm_wrench"
    confidence: float = 0.99


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/state")
async def state() -> Dict[str, Any]:
    return (await orchestrator.snapshot()).to_dict()


@app.post("/api/intent")
async def intent(request: IntentRequest) -> Dict[str, Any]:
    return (await orchestrator.evaluate_intent(request.text)).to_dict()


@app.post("/api/action")
async def action(request: ActionRequest) -> Dict[str, Any]:
    try:
        return (await orchestrator.perform_machine_action(request.action)).to_dict()
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/scenario/{slug}")
async def scenario(slug: str) -> Dict[str, Any]:
    try:
        return (await orchestrator.load_scenario(slug)).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown scenario") from exc


@app.post("/api/worker-zone")
async def worker_zone(request: ZoneRequest) -> Dict[str, Any]:
    return (await orchestrator.set_worker_zone(request.inside)).to_dict()


@app.post("/api/emergency/gas")
async def gas_emergency() -> Dict[str, Any]:
    return (await orchestrator.trigger_gas()).to_dict()


@app.post("/api/emergency/reset")
async def emergency_reset() -> Dict[str, Any]:
    return (await orchestrator.reset_emergency()).to_dict()


@app.post("/api/robot/point")
async def robot_point(request: RobotRequest) -> Dict[str, Any]:
    try:
        return (await orchestrator.point_to_tool(request.target, request.confidence)).to_dict()
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/reset")
async def reset() -> Dict[str, Any]:
    return (await orchestrator.reset()).to_dict()


@app.websocket("/ws")
async def websocket_state(websocket: WebSocket) -> None:
    await websocket.accept()

    async def send(payload: Dict[str, Any]) -> None:
        await websocket.send_json(payload)

    orchestrator.subscribe(send)
    try:
        await send((await orchestrator.snapshot()).to_dict())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        orchestrator.unsubscribe(send)
