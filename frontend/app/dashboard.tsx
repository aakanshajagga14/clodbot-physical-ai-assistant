"use client";

import {
  Bell,
  Bot,
  Camera,
  Check,
  ChevronRight,
  CircleAlert,
  Ellipsis,
  Expand,
  Gauge,
  Hexagon,
  LockKeyhole,
  Mic,
  Orbit,
  Power,
  RotateCcw,
  Send,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Thermometer,
  UserRound,
  Waves,
  Wrench,
  X,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import CyberwaveRobotViewport from "./cyberwave-robot-viewport";

type Machine = {
  name: string;
  power_on: boolean;
  pressure_psi: number;
  isolation_valve_open: boolean;
  lockout_applied: boolean;
  lockout_verified: boolean;
  emergency_stop: boolean;
  worker_in_hazard_zone: boolean;
  gas_ppm: number;
  pressure_cap_removed?: boolean;
};

type Step = { number: number; instruction: string; action: string; status: string; tool?: string };
type EventItem = { sequence: number; timestamp: string; kind: string; title: string; detail: string; severity: string };
type SafetyCheck = { field: string; passed: boolean; actual: unknown; hazard: string };

type World = {
  revision: number;
  machine: Machine;
  robot: { ready: boolean; moving: boolean; action: string; target: string | null; proximity_clear: boolean };
  vision: { worker_detected: boolean; detected_component: string; visible_tools: string[]; camera_online: boolean };
  telemetry: { temperature_c: number; vibration_mm_s: number; gas_ppm: number; sample: number };
  prediction: { phase: string; action: string | null; consequence: string | null; hazard_radius_m: number; worker_exposed: boolean; fidelity: string };
  cyberwave: { status: string; mode: string; sdk_version: string | null; environment_id: string | null; robot_twin_id: string | null; camera_twin_id: string | null; detail: string };
  procedure: { name: string; current_step: number; steps: Step[] };
  safety: { action: string; status: string; authorized: boolean; hazards: string[]; required_actions: string[]; checks: SafetyCheck[] };
  emergency: string;
  current_intent: { text: string; action: string | null; confidence: number; category: string; tool_query: string | null } | null;
  events: EventItem[];
};

type ProcessStage = "idle" | "understanding" | "checking" | "simulating";
type ViewTab = "live" | "prediction" | "history";
type ViewMode = "reset" | "orbit";

const initialWorld: World = {
  revision: 0,
  machine: { name: "Hydraulic Pump A", power_on: false, pressure_psi: 78, isolation_valve_open: true, lockout_applied: true, lockout_verified: false, emergency_stop: false, worker_in_hazard_zone: true, gas_ppm: 0, pressure_cap_removed: false },
  robot: { ready: true, moving: false, action: "SAFE_POSE", target: null, proximity_clear: true },
  vision: { worker_detected: true, detected_component: "filter_housing", visible_tools: ["13mm_wrench", "screwdriver"], camera_online: true },
  telemetry: { temperature_c: 42.1, vibration_mm_s: 0.35, gas_ppm: 0, sample: 0 },
  prediction: { phase: "idle", action: null, consequence: null, hazard_radius_m: 0, worker_exposed: false, fidelity: "DETERMINISTIC CONSEQUENCE MODEL" },
  cyberwave: { status: "CONNECTING", mode: "simulation", sdk_version: null, environment_id: null, robot_twin_id: null, camera_twin_id: null, detail: "Connecting to physical-world layer" },
  procedure: { name: "Hydraulic Filter Replacement", current_step: 3, steps: [] },
  safety: { action: "REMOVE_PRESSURE_CAP", status: "BLOCKED", authorized: false, hazards: [], required_actions: [], checks: [] },
  emergency: "CAUTION",
  current_intent: null,
  events: [],
};

const API = "http://localhost:8000";
const fieldLabels: Record<string, string> = { pressure_psi: "Pressure", isolation_valve_open: "Valve B", power_on: "Power", lockout_applied: "Lockout", lockout_verified: "Zero energy" };

function titleCase(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayActual(field: string, value: unknown) {
  if (field === "pressure_psi") return `${Number(value).toFixed(Number(value) % 1 ? 1 : 0)} PSI`;
  if (field === "isolation_valve_open") return value ? "Open" : "Closed";
  if (field === "power_on") return value ? "On" : "Off";
  if (field === "lockout_applied") return value ? "Active" : "Inactive";
  if (field === "lockout_verified") return value ? "Verified" : "Unverified";
  return String(value);
}

function wait(ms: number) { return new Promise((resolve) => setTimeout(resolve, ms)); }

export default function Dashboard() {
  const [world, setWorld] = useState<World>(initialWorld);
  const [connected, setConnected] = useState(false);
  const [prompt, setPrompt] = useState("Can I remove the pressure cap?");
  const [busy, setBusy] = useState(false);
  const [processStage, setProcessStage] = useState<ProcessStage>("idle");
  const [showPrediction, setShowPrediction] = useState(false);
  const [viewTab, setViewTab] = useState<ViewTab>("live");
  const [viewMode, setViewMode] = useState<ViewMode>("reset");
  const [demoOpen, setDemoOpen] = useState(false);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [procedureOpen, setProcedureOpen] = useState(false);
  const [presentationMode, setPresentationMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const predictionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let fallback: ReturnType<typeof setInterval> | null = null;
    const fetchState = async () => {
      try {
        const response = await fetch(`${API}/api/state`);
        if (response.ok) setWorld(await response.json());
      } catch { setConnected(false); }
    };
    const connect = () => {
      if (stopped) return;
      socket = new WebSocket("ws://localhost:8000/ws");
      socket.onopen = () => { setConnected(true); socket?.send("subscribe"); };
      socket.onmessage = (event) => setWorld(JSON.parse(event.data));
      socket.onerror = () => setConnected(false);
      socket.onclose = () => { setConnected(false); if (!stopped) retry = setTimeout(connect, 1800); };
    };
    fetchState(); connect(); fallback = setInterval(fetchState, 2200);
    return () => { stopped = true; socket?.close(); if (retry) clearTimeout(retry); if (fallback) clearInterval(fallback); };
  }, []);

  const post = async (path: string, body?: object) => {
    setError(null);
    const response = await fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail ?? "Action rejected");
    setWorld(payload);
    return payload as World;
  };

  const askClodbot = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim() || busy) return;
    if (predictionTimer.current) clearTimeout(predictionTimer.current);
    setBusy(true); setShowPrediction(true); setViewTab("prediction"); setProcessStage("understanding");
    const started = Date.now();
    const stageTimers = [setTimeout(() => setProcessStage("checking"), 420), setTimeout(() => setProcessStage("simulating"), 900)];
    try {
      await post("/api/intent", { text: prompt });
      await wait(Math.max(0, 1450 - (Date.now() - started)));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Clodbot is unavailable"); }
    finally {
      stageTimers.forEach(clearTimeout); setProcessStage("idle"); setBusy(false);
      predictionTimer.current = setTimeout(() => { setShowPrediction(false); setViewTab("live"); }, 6500);
    }
  };

  const runAction = async (action: string) => {
    setBusy(true);
    try { await post("/api/action", { action }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Action rejected"); }
    finally { setBusy(false); }
  };

  const runControl = async (path: string, body?: object) => {
    setBusy(true);
    try { await post(path, body); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Control unavailable"); }
    finally { setBusy(false); }
  };

  const startVoiceCommand = () => {
    const browserWindow = window as typeof window & {
      SpeechRecognition?: new () => { lang: string; interimResults: boolean; onresult: (event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void; onerror: () => void; start: () => void };
      webkitSpeechRecognition?: new () => { lang: string; interimResults: boolean; onresult: (event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void; onerror: () => void; start: () => void };
    };
    const Recognition = browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition;
    if (!Recognition) {
      setError("Voice commands are not supported by this browser; type the command instead.");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => setPrompt(event.results[0][0].transcript);
    recognition.onerror = () => setError("Microphone input could not be started.");
    recognition.start();
  };

  const recommendation = useMemo(() => {
    if (world.emergency === "CRITICAL" && world.machine.worker_in_hazard_zone) return { label: "Exit the hazard zone", detail: "Immediate evacuation required", action: "exit-zone" };
    if (world.emergency === "CRITICAL") return { label: "Clear emergency", detail: "Simulate ventilation and reset", action: "reset-emergency" };
    if (world.machine.isolation_valve_open) return { label: "Close Valve B", detail: "Required before cap removal", action: "CLOSE_ISOLATION_VALVE" };
    if (world.machine.pressure_psi > 5) return { label: "Depressurize line", detail: "Reduce pressure below 5 PSI", action: "DEPRESSURIZE" };
    if (!world.machine.lockout_verified) return { label: "Verify zero energy", detail: "Confirm lockout effectiveness", action: "VERIFY_ZERO_ENERGY" };
    if (world.machine.pressure_cap_removed) return { label: "Remove used filter", detail: "Energy state remains verified", action: "REMOVE_FILTER" };
    return { label: "Remove pressure cap", detail: "All prerequisites satisfied", action: "REMOVE_PRESSURE_CAP" };
  }, [world]);

  const executeRecommendation = () => recommendation.action === "exit-zone"
    ? runControl("/api/worker-zone", { inside: false })
    : recommendation.action === "reset-emergency"
      ? runControl("/api/emergency/reset")
      : runAction(recommendation.action);

  const assistantText = world.emergency === "CRITICAL"
    ? world.machine.worker_in_hazard_zone
      ? `Gas is at ${world.machine.gas_ppm.toFixed(0)} ppm. Leave the cell immediately.`
      : `Worker evacuation confirmed. Ventilate the cell and clear the emergency before re-entry.`
    : world.safety.status === "SAFE"
      ? `Zero energy is verified. Pressure is ${world.machine.pressure_psi.toFixed(0)} PSI; the maintenance step is authorized.`
      : `The line is still pressurized${world.machine.isolation_valve_open ? " and Valve B is open" : ""}. ${world.safety.required_actions[0] ?? "Complete isolation before continuing"}.`;

  const predictionActive = showPrediction && Boolean(world.prediction.consequence?.includes("RELEASE"));

  return (
    <main className={`desktop-canvas ${presentationMode ? "presentation-mode" : ""}`}>
      <section className="command-shell">
        <TopCommandBar world={world} connected={connected} prompt={prompt} busy={busy} onPrompt={setPrompt} onSubmit={askClodbot} onVoice={startVoiceCommand} onEvents={() => setEventsOpen(true)} onDemo={() => setDemoOpen(true)} />
        {world.emergency === "CRITICAL" ? <div className="emergency-line"><CircleAlert size={13} /><b>Critical gas event</b><span>{world.machine.gas_ppm.toFixed(0)} ppm detected</span><button disabled={busy || !world.machine.worker_in_hazard_zone} onClick={() => runControl("/api/worker-zone", { inside: false })}>{world.machine.worker_in_hazard_zone ? "Evacuate worker" : "Worker evacuated"}</button></div> : <div className="emergency-spacer" />}
        <div className="workspace-grid">
          <PerceptionColumn world={world} onRobotInspect={() => { setViewMode("orbit"); setViewTab("live"); }} />
          <DigitalTwinWorkspace world={world} viewTab={viewTab} onViewTab={setViewTab} viewMode={viewMode} onViewMode={setViewMode} onExpand={() => setPresentationMode((value) => !value)} predictionActive={predictionActive} processStage={processStage} />
          <IntelligenceColumn world={world} processStage={processStage} recommendation={recommendation} assistantText={assistantText} busy={busy} error={error} onRecommendation={executeRecommendation} onViewProcedure={() => setProcedureOpen(true)} onDismissError={() => setError(null)} />
        </div>
      </section>
      <DemoDrawer open={demoOpen} world={world} busy={busy} presentationMode={presentationMode} onPresentation={() => setPresentationMode((value) => !value)} onClose={() => setDemoOpen(false)} onControl={runControl} onAction={runAction} />
      <EventsDrawer open={eventsOpen} events={world.events} onClose={() => setEventsOpen(false)} />
      <ProcedureDrawer open={procedureOpen} world={world} onClose={() => setProcedureOpen(false)} />
    </main>
  );
}

function TopCommandBar({ world, connected, prompt, busy, onPrompt, onSubmit, onVoice, onEvents, onDemo }: { world: World; connected: boolean; prompt: string; busy: boolean; onPrompt: (value: string) => void; onSubmit: (event: FormEvent) => void; onVoice: () => void; onEvents: () => void; onDemo: () => void }) {
  const cyberwaveLabel = world.cyberwave.status === "CONNECTED" ? (world.cyberwave.mode === "live" ? "Live" : "Connected") : "Simulated";
  return <header className="command-bar">
    <div className="brand-lockup"><div className="brand-mark"><Hexagon size={18} strokeWidth={1.7} /><i></i></div><div><strong>Clodbot</strong><span><i className={connected ? "connected" : ""}></i>Maintenance Cell 01</span></div></div>
    <form className="command-field" onSubmit={onSubmit}><Send size={13} /><input aria-label="Ask Clodbot" value={prompt} onChange={(event) => onPrompt(event.target.value)} placeholder="Ask Clodbot or enter a command…" /><button type="button" aria-label="Voice command" onClick={onVoice}><Mic size={14} /></button><button className="run-command" type="submit" disabled={busy || !prompt.trim()}>Run</button></form>
    <div className="command-actions"><div className="compact-status"><span>Simulation</span><b>Active</b></div><div className="compact-status"><span>Cyberwave</span><b><i className={world.cyberwave.status === "CONNECTED" ? "live" : "simulated"}></i>{cyberwaveLabel}</b></div><button aria-label="Notifications" onClick={onEvents}><Bell size={15} /></button><button aria-label="Settings" onClick={onDemo}><Settings size={15} /></button><button aria-label="Open demo controls" onClick={onDemo}><Ellipsis size={17} /></button></div>
  </header>;
}

function PerceptionColumn({ world, onRobotInspect }: { world: World; onRobotInspect: () => void }) {
  return <aside className="perception-column">
    <ColumnHeading title="Perception" count="3" />
    <VisionFeedCard title="Camera 01" subtitle="Cyberwave camera twin" status={world.cyberwave.camera_twin_id && world.vision.camera_online ? "LIVE" : "NOT PAIRED"} className="overview-feed" icon={<Camera size={11} />} disabled={!world.cyberwave.camera_twin_id}>
      <div className="camera-twin-placeholder"><Camera size={19} /><span>Camera twin</span><small>Connect a Cyberwave camera to stream frames</small></div>
    </VisionFeedCard>
    <VisionFeedCard title="SO-101 Arm" subtitle="Cyberwave catalog twin" status={world.robot.moving ? "MOVING" : "TWIN READY"} className="robot-feed" icon={<Bot size={11} />} onInspect={onRobotInspect}>
      <CyberwaveRobotViewport compact action={world.robot.action} moving={world.robot.moving} viewMode="orbit" />
    </VisionFeedCard>
    <ColumnHeading title="System status" count="2" />
    <div className="status-card-grid">
      <article className="unit-card dark"><header><div><b>SO-101</b><span>Tool station</span></div><i className={world.robot.ready ? "ready" : ""}></i></header><div className="unit-orbit"><Bot size={26} /><span></span></div><footer><span>Safety</span><strong>{world.robot.proximity_clear ? "100%" : "72%"}</strong></footer></article>
      <article className="unit-card pump"><header><div><b>Hydraulic Pump A</b><span>Maintenance</span></div><Gauge size={14} /></header><div className="pressure-reading"><span>Pressure</span><strong>{world.machine.pressure_psi.toFixed(0)}<small> PSI</small></strong></div><footer><span className={world.machine.lockout_applied ? "locked" : "warning"}>{world.machine.lockout_applied ? "LOCKED OUT" : "UNLOCKED"}</span></footer></article>
    </div>
  </aside>;
}

function ColumnHeading({ title, count }: { title: string; count: string }) { return <div className="column-heading"><strong>{title}</strong><span>{count}</span></div>; }

function VisionFeedCard({ title, subtitle, status, className, icon, children, disabled = false, onInspect }: { title: string; subtitle: string; status: string; className: string; icon: ReactNode; children: ReactNode; disabled?: boolean; onInspect?: () => void }) {
  return <article className="vision-card"><div className={`vision-image ${className}`}>{children}<div className="feed-status"><i></i>{status}</div><span className="scan-corner tl"></span><span className="scan-corner br"></span></div><footer><div><strong>{title}</strong><span>{subtitle}</span></div><button aria-label={`Inspect ${title}`} disabled={disabled} title={disabled ? "No camera twin is paired" : undefined} onClick={onInspect}>{icon}</button></footer></article>;
}

function DigitalTwinWorkspace({ world, viewTab, onViewTab, viewMode, onViewMode, onExpand, predictionActive, processStage }: { world: World; viewTab: ViewTab; onViewTab: (tab: ViewTab) => void; viewMode: ViewMode; onViewMode: (mode: ViewMode) => void; onExpand: () => void; predictionActive: boolean; processStage: ProcessStage }) {
  const viewingPrediction = viewTab === "prediction" || predictionActive;
  return <section className="twin-workspace">
    <header className="workspace-heading"><div><strong>Facility Overview</strong><span>Hydraulic Station A · Cell 01</span></div><nav aria-label="Digital twin views">{(["live", "prediction", "history"] as ViewTab[]).map((tab) => <button key={tab} className={viewTab === tab ? "active" : ""} onClick={() => onViewTab(tab)}>{titleCase(tab)}</button>)}</nav></header>
    <div className={`scene-viewport ${viewMode === "orbit" ? "orbiting" : ""} ${viewingPrediction ? "prediction-view" : ""}`}>
      <CyberwaveRobotViewport action={world.robot.action} moving={world.robot.moving} viewMode={viewMode} />
      <div className="scene-vignette"></div>
      <div className="scene-meta"><span><i></i>{world.cyberwave.status === "CONNECTED" ? (world.cyberwave.mode === "live" ? "CYBERWAVE · LIVE" : "CYBERWAVE · PLAYGROUND") : "SO-101 CATALOG TWIN"}</span><b>SO-101 · 6-DOF</b></div>
      {viewTab === "history" && <div className="history-overlay"><span>RECORDED STATE</span><strong>Latest safety event</strong><small>{world.events[0]?.title ?? "No recorded events"}</small></div>}
      <ScenePin className="cap-pin" label="Pressure cap" value={world.safety.status === "SAFE" ? "Ready" : "Restricted"} tone={world.safety.status === "SAFE" ? "safe" : "danger"} />
      <ScenePin className="valve-pin" label="Valve B" value={world.machine.isolation_valve_open ? "Open" : "Closed"} tone={world.machine.isolation_valve_open ? "warning" : "safe"} />
      <ScenePin className="worker-pin" label="Worker 01" value={world.machine.worker_in_hazard_zone ? "Exposed" : "Clear"} tone={world.machine.worker_in_hazard_zone ? "danger" : "safe"} />
      {viewingPrediction && <><div className="prediction-scrim"></div><div className="prediction-label"><Waves size={12} /><div><span>PREDICTED STATE</span><strong>Potential hydraulic release</strong></div><b>{world.machine.pressure_psi.toFixed(0)} PSI</b></div><div className="hazard-zone"></div><div className="fluid-plume"><i></i><i></i><i></i><i></i></div></>}
      {processStage !== "idle" && <div className="analysis-stage"><i></i><span>{processStage === "understanding" ? "Understanding intent" : processStage === "checking" ? "Reading machine state" : "Simulating consequence"}</span></div>}
      <div className="floating-controls"><button onClick={() => onViewMode("reset")} className={viewMode === "reset" ? "active" : ""}><RotateCcw size={13} />Reset</button><button onClick={() => onViewMode("orbit")} className={viewMode === "orbit" ? "active" : ""}><Orbit size={13} />Orbit view</button><button aria-label="Expand viewport" onClick={onExpand}><Expand size={13} /></button></div>
      <TelemetryOverlay world={world} />
    </div>
  </section>;
}

function ScenePin({ className, label, value, tone }: { className: string; label: string; value: string; tone: string }) { return <div className={`scene-pin ${className} ${tone}`}><i></i><div><span>{label}</span><strong>{value}</strong></div></div>; }

function TelemetryOverlay({ world }: { world: World }) {
  return <div className="telemetry-overlay"><TelemetryItem icon={<Gauge size={12} />} label="Pressure" value={`${world.machine.pressure_psi.toFixed(0)} PSI`} alert={world.machine.pressure_psi > 5} /><TelemetryItem icon={<Thermometer size={12} />} label="Temperature" value={`${world.telemetry.temperature_c.toFixed(1)}°`} /><TelemetryItem icon={<Waves size={12} />} label="Vibration" value={world.telemetry.vibration_mm_s.toFixed(2)} /><TelemetryItem icon={<CircleAlert size={12} />} label="Gas" value={`${world.machine.gas_ppm.toFixed(0)} ppm`} alert={world.machine.gas_ppm >= 50} /></div>;
}

function TelemetryItem({ icon, label, value, alert = false }: { icon: ReactNode; label: string; value: string; alert?: boolean }) { return <div className={alert ? "alert" : ""}>{icon}<span>{label}</span><strong>{value}</strong></div>; }

function IntelligenceColumn({ world, processStage, recommendation, assistantText, busy, error, onRecommendation, onViewProcedure, onDismissError }: { world: World; processStage: ProcessStage; recommendation: { label: string; detail: string; action: string }; assistantText: string; busy: boolean; error: string | null; onRecommendation: () => void; onViewProcedure: () => void; onDismissError: () => void }) {
  const isSafe = world.safety.status === "SAFE";
  const isCritical = world.emergency === "CRITICAL";
  const checks = world.safety.checks.filter((check) => check.field !== "lockout_verified").slice(0, 4);
  const consequence = isSafe ? "No hazardous consequence" : world.prediction.consequence?.includes("RELEASE") ? "Hydraulic fluid release" : "Unsafe maintenance state";
  return <aside className="intelligence-column">
    <ColumnHeading title="Clodbot Intelligence" count="AI" />
    <section className={`decision-module ${isCritical ? "critical" : isSafe ? "safe" : "blocked"} ${processStage !== "idle" ? "processing" : ""}`}><header><div><span>Predictive Safety</span><small>{processStage !== "idle" ? "Analyzing physical state" : "Deterministic authorization"}</small></div><ShieldCheck size={15} /></header><div className="decision-status"><div><b>{processStage !== "idle" ? "ANALYZING" : isCritical ? "CRITICAL" : isSafe ? "SAFE" : "BLOCKED"}</b><span>{titleCase(world.safety.action)}</span></div><i>{isSafe ? <Check size={15} /> : <CircleAlert size={15} />}</i></div><div className="consequence"><span>Predicted consequence</span><strong>{consequence}</strong></div><div className="check-table">{checks.map((check) => <div key={check.field}><span>{fieldLabels[check.field] ?? titleCase(check.field)}</span><strong>{displayActual(check.field, check.actual)}</strong><i className={check.passed ? "pass" : "fail"}>{check.passed ? <Check size={10} /> : <CircleAlert size={10} />}</i></div>)}</div></section>
    <button className="next-action" disabled={busy} onClick={onRecommendation}><div><span>Next action</span><strong>{recommendation.label}</strong><small>{recommendation.detail}</small></div><ChevronRight size={15} /></button>
    <ProcedureTimeline world={world} onViewAll={onViewProcedure} />
    <section className="clodbot-insight"><header><div className="insight-mark"><Hexagon size={14} /><i></i></div><div><strong>Clodbot</strong><span>Physical reasoning</span></div></header><p>{assistantText}</p><button disabled={busy} onClick={onRecommendation}>{world.machine.isolation_valve_open ? "Highlight valve" : "Continue procedure"}<ChevronRight size={12} /></button></section>
    {error && <div className="inline-error"><CircleAlert size={12} /><span>{error}</span><button onClick={onDismissError}><X size={11} /></button></div>}
  </aside>;
}

function ProcedureTimeline({ world, onViewAll }: { world: World; onViewAll: () => void }) {
  const currentIndex = Math.max(0, world.procedure.steps.findIndex((step) => step.status === "current"));
  const start = Math.max(0, currentIndex - 2);
  const shown = world.procedure.steps.slice(start, start + 5);
  return <section className="timeline-module"><header><div><span>Maintenance Procedure</span><strong>Filter replacement</strong></div><button onClick={onViewAll}>View all</button></header><div className="timeline">{shown.map((step, index) => <div key={step.number} className={step.status}><time>{`08:${String(31 + start + index).padStart(2, "0")}`}</time><i>{step.status === "complete" ? <Check size={9} /> : ""}</i><div><strong>{step.instruction}</strong>{step.status === "current" && <span>REQUIRED</span>}</div></div>)}</div></section>;
}

function DemoDrawer({ open, world, busy, presentationMode, onPresentation, onClose, onControl, onAction }: { open: boolean; world: World; busy: boolean; presentationMode: boolean; onPresentation: () => void; onClose: () => void; onControl: (path: string, body?: object) => void; onAction: (action: string) => void }) {
  return <><button className={`drawer-backdrop ${open ? "open" : ""}`} onClick={onClose} aria-label="Close demo controls"></button><aside className={`side-drawer ${open ? "open" : ""}`} aria-hidden={!open}><header><div><span>Demo controls</span><small>Operator tools</small></div><button onClick={onClose} aria-label="Close demo controls"><X size={17} /></button></header><fieldset className="drawer-controls" disabled={busy}><DrawerGroup title="View" icon={<Settings size={14} />}><button onClick={onPresentation}>{presentationMode ? "Exit" : "Enter"} presentation mode</button></DrawerGroup><DrawerGroup title="Scenarios" icon={<SlidersHorizontal size={14} />}><button onClick={() => onControl("/api/scenario/unsafe")}>Unsafe hydraulic repair</button><button onClick={() => onControl("/api/scenario/correct")}>Safe maintenance</button><button onClick={() => onControl("/api/scenario/gas")}>Gas leak</button><button onClick={() => onControl("/api/scenario/tool")}>Tool assistance</button></DrawerGroup><DrawerGroup title="Machine" icon={<Gauge size={14} />}><button onClick={() => onAction(world.machine.power_on ? "TURN_OFF_POWER" : "START_MACHINE")}><Power size={13} />Power {world.machine.power_on ? "off" : "on"}</button><button onClick={() => onAction(world.machine.isolation_valve_open ? "CLOSE_ISOLATION_VALVE" : "OPEN_ISOLATION_VALVE")}>Valve {world.machine.isolation_valve_open ? "close" : "open"}</button><button onClick={() => onAction(world.machine.lockout_applied ? "REMOVE_LOCKOUT" : "APPLY_LOCKOUT")}><LockKeyhole size={13} />{world.machine.lockout_applied ? "Remove" : "Apply"} lockout</button><button className="primary" onClick={() => onAction("DEPRESSURIZE")}>Depressurize line</button></DrawerGroup><DrawerGroup title="Worker & robot" icon={<Bot size={14} />}><button onClick={() => onControl("/api/worker-zone", { inside: !world.machine.worker_in_hazard_zone })}><UserRound size={13} />{world.machine.worker_in_hazard_zone ? "Exit" : "Enter"} hazard zone</button><button onClick={() => onControl("/api/robot/point", { target: "13mm_wrench", confidence: 0.99 })}><Wrench size={13} />Point to wrench</button></DrawerGroup><button className="reset-demo" onClick={() => onControl("/api/reset")}><RotateCcw size={14} />Reset complete demo</button></fieldset></aside></>;
}

function DrawerGroup({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) { return <section className="drawer-group"><h3>{icon}{title}</h3><div>{children}</div></section>; }

function ProcedureDrawer({ open, world, onClose }: { open: boolean; world: World; onClose: () => void }) {
  return <><button className={`drawer-backdrop ${open ? "open" : ""}`} onClick={onClose} aria-label="Close procedure"></button><aside className={`side-drawer procedure-drawer ${open ? "open" : ""}`} aria-hidden={!open}><header><div><span>Filter replacement</span><small>Full maintenance procedure</small></div><button onClick={onClose} aria-label="Close procedure"><X size={17} /></button></header><div className="full-procedure">{world.procedure.steps.map((step) => <div className={step.status} key={step.number}><b>{step.status === "complete" ? <Check size={12} /> : step.number}</b><div><strong>{step.instruction}</strong><span>{titleCase(step.action)}{step.tool ? ` · ${step.tool}` : ""}</span></div>{step.status === "current" && <i>Current</i>}</div>)}</div></aside></>;
}

function EventsDrawer({ open, events, onClose }: { open: boolean; events: EventItem[]; onClose: () => void }) {
  return <><button className={`drawer-backdrop ${open ? "open" : ""}`} onClick={onClose} aria-label="Close event log"></button><aside className={`side-drawer events-drawer ${open ? "open" : ""}`} aria-hidden={!open}><header><div><span>Event log</span><small>Live safety and robot activity</small></div><button onClick={onClose} aria-label="Close event log"><X size={17} /></button></header><div className="event-list">{events.length ? events.map((event) => <article key={event.sequence} className={event.severity}><i></i><div><strong>{event.title}</strong><span>{event.detail || titleCase(event.kind)}</span></div><time>{new Date(event.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></article>) : <p>No events recorded yet.</p>}</div></aside></>;
}
