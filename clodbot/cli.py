import argparse
from typing import Optional

from clodbot.core.enums import SafetyStatus, WorkerAction
from clodbot.core.world_state import MachineState
from clodbot.procedures import ProcedureEngine
from clodbot.safety import SafetyDecision, SafetyEngine
from clodbot.simulation.scenarios import SCENARIOS
from clodbot.intent import RuleIntentProvider


def parse_demo_phrase(text: str) -> Optional[WorkerAction]:
    """Small, closed vocabulary for the demo—not an AI intent provider."""
    return RuleIntentProvider().parse(text).action


def _state_panel(state: MachineState) -> str:
    return "\n".join([
        f"Pressure..............{state.pressure_psi:g} PSI",
        f"Isolation valve.......{'OPEN' if state.isolation_valve_open else 'CLOSED'}",
        f"Power.................{'ON' if state.power_on else 'OFF'}",
        f"Lockout...............{'ACTIVE' if state.lockout_applied else 'NOT APPLIED'}",
    ])


def _decision_panel(decision: SafetyDecision) -> str:
    symbol = "✓" if decision.status is SafetyStatus.SAFE else "✕"
    lines = [f"{symbol} ACTION {decision.status.value}"]
    if decision.hazards:
        lines.extend(["", *decision.hazards])
    if decision.required_actions:
        lines.extend(["", "Required before continuing:"])
        lines.extend(f"{i}. {item}." for i, item in enumerate(decision.required_actions, 1))
    return "\n".join(lines)


def run_demo(scenario_slug: str = "unsafe") -> SafetyDecision:
    scenario = SCENARIOS[scenario_slug]
    procedure = ProcedureEngine()
    procedure.reconcile(scenario.state)
    safety = SafetyEngine()
    prompt = "Can I remove the pressure cap?"
    action = parse_demo_phrase(prompt)
    assert action is not None
    decision = safety.evaluate(scenario.proposed_action, scenario.state)

    print("═" * 62)
    print("  CLODBOT // INDUSTRIAL SAFETY COPILOT  [SIMULATION]")
    print("═" * 62)
    print(f"Machine:   {scenario.state.name}")
    print(f"Procedure: {procedure.name}")
    print(f"Scenario:  {scenario.title}\n")
    print(_state_panel(scenario.state))
    print(f"\nWORKER\n> {prompt}\n\nCLODBOT")
    print(_decision_panel(decision))
    print("\n" + "─" * 62)
    print(f"Procedure step {procedure.current_step.number}/{len(procedure.steps)}: "
          f"{procedure.current_step.instruction}")
    if scenario_slug == "tool":
        print("Required tool: 13 mm wrench  // Robot assistance: DRY RUN")
    if scenario_slug == "gas":
        print(f"⚠ CRITICAL SAFETY EVENT // GAS {scenario.state.gas_ppm:g} PPM // EVACUATE")
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic Clodbot Phase 1 demo")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="unsafe")
    args = parser.parse_args()
    run_demo(args.scenario)


if __name__ == "__main__":
    main()
