from dataclasses import dataclass
from typing import Dict, Optional

from clodbot.core.enums import WorkerAction


@dataclass(frozen=True)
class IntentResult:
    action: Optional[WorkerAction]
    confidence: float
    category: str = "worker_action"
    tool_query: Optional[str] = None


class RuleIntentProvider:
    """Fail-closed offline intent provider for the typed Phase 2 demo."""

    PHRASES: Dict[str, WorkerAction] = {
        "can i remove the pressure cap?": WorkerAction.REMOVE_PRESSURE_CAP,
        "can i remove this cap?": WorkerAction.REMOVE_PRESSURE_CAP,
        "i'm going to open the housing.": WorkerAction.REMOVE_PRESSURE_CAP,
        "take this filter out.": WorkerAction.REMOVE_FILTER,
        "can i start the machine?": WorkerAction.START_MACHINE,
        "close isolation valve": WorkerAction.CLOSE_ISOLATION_VALVE,
        "close valve b": WorkerAction.CLOSE_ISOLATION_VALVE,
        "depressurize": WorkerAction.DEPRESSURIZE,
    }

    def parse(self, text: str) -> IntentResult:
        normalized = " ".join(text.strip().lower().split())
        if "which tool" in normalized or "what tool" in normalized:
            return IntentResult(None, 0.99, category="tool_query", tool_query="13mm_wrench")
        action = self.PHRASES.get(normalized)
        return IntentResult(action, 0.99 if action else 0.0, category="worker_action")
