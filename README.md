# Clodbot

**Predictive physical AI for industrial worker safety.**

Clodbot is a safety copilot that reasons about what a worker intends to do, reads
the physical state of a workstation, and predicts whether the next action is
safe. Conventional monitoring often reacts after a rule is broken; Clodbot puts
a deterministic safety gate before the action and explains how to make it safe.

The repository now includes the Phase 1 deterministic foundation and a Phase 2
digital-twin demonstration: one canonical real-time world state, a Cyberwave
adapter with transparent mock fallback, deterministic consequence simulation,
robot motion gating, structured event memory, and an industrial command UI.

## Safety architecture

```text
camera / voice / telemetry (future)
                 │
                 ▼
       untrusted perception + intent
                 │ symbolic action enum only
                 ▼
      ┌─────────────────────────┐
      │ DETERMINISTIC SAFETY GATE│◄── immutable machine state
      └────────────┬────────────┘    + versioned rules/SOP
             SAFE │       │ BLOCKED / CAUTION
                  ▼       ▼
       simulator / robot   warning + corrective steps
       adapter (future)
```

Model output will never authorize physical actions. Only predefined action
enums can cross the safety boundary, and execution must revalidate current
state. Simulation is the default; future live mode requires explicit opt-in.

## Run it

Python 3.9+ is supported. The Phase 1 runtime has no third-party dependency.

### Digital-twin dashboard

Install once, then launch both services from one terminal:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dashboard,dev]'
cd frontend && pnpm install && cd ..
./run_clodbot.sh
```

Open [http://localhost:3000](http://localhost:3000). Cyberwave mock mode is the
default and is visibly labeled `MOCK`. To use the verified Cyberwave 0.6.4 path,
run Python 3.10+, install the `cyberwave` extra, configure existing environment,
SO-101, and camera twin IDs, then set `CLODBOT_CYBERWAVE_MOCK=false`.

The default Cyberwave simulation runtime is `playground`; switching to MuJoCo
must be explicit because current SDK `affect("simulation")` can start a billable
cloud simulation instance.

Flagship sequence:

1. Ask “Can I remove the pressure cap?” — Clodbot predicts pressurized release.
2. Open the operator drawer and close isolation valve B.
3. Start depressurization and watch pressure decay over several updates.
4. At less than 5 PSI, zero energy is verified and safety changes to `SAFE`.
5. Ask the same question again — the action is now authorized.

```bash
python3 -m clodbot.cli --scenario unsafe
python3 -m clodbot.cli --scenario correct
python3 -m clodbot.cli --scenario gas
python3 -m clodbot.cli --scenario tool
```

Run the safety-critical tests:

```bash
python3 -m pytest
```

## Current structure

```text
clodbot/
├── core/          # typed enums and immutable machine state
├── safety/        # deterministic engine + external hydraulic rules
├── simulation/    # transition-safe machine and four scenarios
├── procedures/    # ordered SOP engine + hydraulic filter procedure
├── cyberwave/     # verified SDK adapter plus transparent mock world
├── orchestrator/  # canonical world state and real-time event loop
├── prediction/    # deterministic consequence simulation
├── robotics/      # semantic robot action safety gate
├── api/           # FastAPI state, controls, and WebSocket transport
└── cli.py         # repeatable terminal demo
frontend/           # industrial React/vinext command interface
tests/              # safety, simulator, procedure, fail-closed tests
```

The `.yaml` configuration files use JSON syntax, which is valid YAML. This keeps
the safety core dependency-free while making the rules portable to a full YAML
loader later.

## Cyberwave integration boundary

The Cyberwave SDK is intentionally optional and is not installed in the current
environment. Current official SDK documentation uses:

```python
from cyberwave import Cyberwave

cw = Cyberwave()                         # CYBERWAVE_API_KEY
cw.affect("simulation")                  # explicit execution target
arm = cw.twin("the-robot-studio/so101") # documented catalog twin
```

One adapter owns connection, twin lookup, camera capture, alerts, and named
joint commands. The independent safety engine remains the only worker-action
authorization boundary. The robot gate accepts only semantic predefined actions
and maps them to a fixed, reviewed pointing pose after emergency, readiness,
proximity, target, and confidence checks.

Official references consulted:

- [Cyberwave Python SDK](https://github.com/cyberwave-os/cyberwave-python)
- [Cyberwave API overview](https://docs.cyberwave.com/api-reference/overview)
- [SO-101 hardware and twin overview](https://docs.cyberwave.com/hardware/so101)

## Demo scenarios

1. `unsafe` — a pressurized line blocks cap removal and gives corrections.
2. `correct` — verified zero energy authorizes cap removal.
3. `gas` — 82 ppm gas plus emergency stop blocks all normal activity.
4. `tool` — safe removal identifies the required 13 mm wrench in dry-run mode.

## Simulation versus hardware

The simulator enforces physical invariants even if application code forgets to
call the safety engine. Real hardware is not supported yet. Credentials belong
in environment variables, never source control. A physical deployment will also
require a site-specific risk assessment, independent certified safety controls,
motion limits, guarded zones, and a hardware emergency stop; Clodbot is not a
substitute for those controls.

## Phase 2 scope boundaries

The scene is an application-rendered structured digital-twin view when Cyberwave
camera frames are unavailable; it never claims to be photorealistic CAD or CFD.
The consequence overlay is explicitly a deterministic rules-based model. Robot
pointing is supported in mock mode and through fixed named SO-101 joint targets
in configured Cyberwave mode. Voice, VLMs, autonomous manipulation, cloud
deployment, and additional machines remain out of scope.

Screenshot placeholder: `docs/images/phase-1-cli.png`
