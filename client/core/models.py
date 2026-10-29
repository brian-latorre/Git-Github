from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

class InputType(str, Enum):
    SINGLE = "single"
    COMBINATION = "combination"
    COMMAND = "command"

@dataclass(frozen=True)
class NormalizedInputEvent:

    input_type: InputType
    canonical_repr: str          # Ej: 'ctrl+s', 'ctrl+shift+v', 'f5', 'cmd:git status'
    raw_key: str
    modifiers: Set[str] = field(default_factory=set)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    @property
    def formatted_time(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")

@dataclass
class TargetRule:

    id: str
    label: str
    input_type: InputType
    pattern: str                 # Ej: 'ctrl+s', 'git status', 'f5'
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "input_type": self.input_type.value,
            "pattern": self.pattern,
            "description": self.description,
        }

@dataclass
class StudentSession:

    student_id: str
    display_name: str
    sid: Optional[str] = None
    online: bool = True
    last_event: Optional[NormalizedInputEvent] = None
    last_activity_time: Optional[datetime] = None
    completed_targets: Set[str] = field(default_factory=set)
    completed_challenges_history: Set[str] = field(default_factory=set)
    total_actions_count: int = 0
    activity_history: List[Dict] = field(default_factory=list)

    @property
    def score(self) -> int:

        return len(self.completed_challenges_history)

    @property
    def is_current_target_completed(self) -> bool:

        return False

    def to_dict(self, active_target_id: Optional[str] = None) -> Dict:
        is_completed = (active_target_id in self.completed_targets) if active_target_id else False
        return {
            "student_id": self.student_id,
            "display_name": self.display_name,
            "online": self.online,
            "last_key": self.last_event.canonical_repr if self.last_event else None,
            "last_time": self.last_event.formatted_time if self.last_event else None,
            "is_completed": is_completed,
            "total_actions": self.total_actions_count,
            "challenges_completed": len(self.completed_challenges_history),
            "score": self.score,
            "completed_targets": list(self.completed_targets),
            "activity_history": self.activity_history[-14:],
        }
