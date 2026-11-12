from dataclasses import dataclass, field, asdict
from typing import Any

SEV_ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


@dataclass
class Finding:
    severity: str            # INFO | WARNING | CRITICAL
    source: str              # e.g. cm.service, cm.host, cm.role, ts.threshold, ts.anomaly, ts.forecast
    subject: str             # service / host / role / metric entity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def at_least(sev: str, floor: str) -> bool:
    return SEV_ORDER[sev] >= SEV_ORDER[floor]
