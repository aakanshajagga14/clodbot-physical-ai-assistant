from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    timestamp: str
    kind: str
    title: str
    detail: str = ""
    severity: str = "info"

    @classmethod
    def create(
        cls, sequence: int, kind: str, title: str, detail: str = "", severity: str = "info"
    ) -> "EventRecord":
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return cls(sequence, now, kind, title, detail, severity)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
