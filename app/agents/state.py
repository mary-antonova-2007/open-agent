from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.application.schemas import EmployeeContext


@dataclass
class AgentState:
    employee: EmployeeContext
    text: str
    source: str
    trace_id: str
    route: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    response: str | None = None
