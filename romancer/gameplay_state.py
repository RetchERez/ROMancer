from __future__ import annotations

"""ROMancer v9 game-state and session-memory model."""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


COMMON_STATES = {
    "BOOT","TITLE","MAIN_MENU","SETTINGS","FILE_SELECT","CHARACTER_SELECT","TUTORIAL",
    "CUTSCENE","DIALOGUE","DIALOGUE_CHOICE","EXPLORATION","COMBAT","COMBAT_COMMAND",
    "COMBAT_TARGET","PUZZLE","SHOP","INVENTORY","EQUIPMENT","MAP","QUEST_LOG",
    "TACTICAL_PHASE","CRAFTING","RESULTS","DEATH","GAME_OVER","PAUSED","LOADING",
    "CREDITS","POSTGAME","UNKNOWN"
}


@dataclass
class ObjectiveRecord:
    verb: str | None = None
    target: str | None = None
    destination: str | None = None
    condition: str | None = None
    deadline: str | None = None
    completion_signal: str | None = None
    source: str | None = None
    confidence: str = "UNKNOWN"
    status: str = "active"


@dataclass
class SessionState:
    title: str | None = None
    platform: str | None = None
    region: str | None = None
    version: str | None = None
    mode: str | None = None
    rom_sha256: str | None = None
    current_state: str = "UNKNOWN"
    location: str | None = None
    position: list[int] | None = None
    camera_orientation: str | None = None
    objective: ObjectiveRecord | None = None
    next_destination: str | None = None
    health: float | None = None
    max_health: float | None = None
    core_resource: float | None = None
    lives_or_retries: float | None = None
    currency: float | None = None
    status_effects: list[str] = field(default_factory=list)
    key_items: list[str] = field(default_factory=list)
    healing_items: dict[str, float] = field(default_factory=dict)
    important_materials: dict[str, float] = field(default_factory=dict)
    equipment: dict[str, str] = field(default_factory=dict)
    party: list[dict[str, Any]] = field(default_factory=list)
    enemies: list[dict[str, Any]] = field(default_factory=list)
    interactables: list[dict[str, Any]] = field(default_factory=list)
    known_exits: list[dict[str, Any]] = field(default_factory=list)
    blocked_routes: list[dict[str, Any]] = field(default_factory=list)
    npcs_to_revisit: list[str] = field(default_factory=list)
    map_knowledge: dict[str, Any] = field(default_factory=dict)
    control_map: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    last_action: dict[str, Any] | None = None
    observed_result: dict[str, Any] | None = None
    last_real_save: str | None = None
    last_checkpoint: str | None = None
    risk_since_save: str = "unknown"
    last_completed_objective: str | None = None
    recently_acquired: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> list[str]:
        issues=[]
        if self.current_state not in COMMON_STATES:
            issues.append(f"nonstandard current_state {self.current_state!r}; use UNKNOWN or a documented extension")
        if self.health is not None and self.max_health is not None and self.health > self.max_health:
            issues.append("health exceeds max_health")
        return issues

    def transition(self, new_state: str, *, evidence: str | None = None) -> dict[str, Any]:
        old=self.current_state
        self.current_state=new_state
        self.updated_at=datetime.now(timezone.utc).isoformat()
        return {"from":old,"to":new_state,"evidence":evidence,"verified":bool(evidence)}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "SessionState":
        o=dict(obj)
        if isinstance(o.get("objective"),dict): o["objective"]=ObjectiveRecord(**o["objective"])
        return cls(**{k:v for k,v in o.items() if k in cls.__dataclass_fields__})

    @classmethod
    def load(cls,path:str|Path)->"SessionState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self,path:str|Path)->str:
        p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(self.to_dict(),indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return str(p)
