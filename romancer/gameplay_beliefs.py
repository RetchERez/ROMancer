from __future__ import annotations

"""Evidence-scoped gameplay beliefs for ROMancer v9.

A belief is not automatically a fact.  ROMancer deliberately distinguishes verified
observations from conventions and hypotheses so autonomous play cannot silently turn a
common genre habit into a game-specific rule.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
import json


class BeliefStatus(str, Enum):
    VERIFIED = "VERIFIED"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    PLAUSIBLE = "PLAUSIBLE"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"


STATUS_SCORE = {
    BeliefStatus.VERIFIED: 1.0,
    BeliefStatus.HIGH_CONFIDENCE: 0.8,
    BeliefStatus.PLAUSIBLE: 0.45,
    BeliefStatus.UNKNOWN: 0.0,
    BeliefStatus.CONTRADICTED: 0.0,
}


@dataclass
class Belief:
    claim: str
    status: BeliefStatus = BeliefStatus.UNKNOWN
    confidence: float = 0.0
    context: str = "global"
    evidence: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    source: str | None = None
    rom_sha256: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def normalize(self) -> "Belief":
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.status == BeliefStatus.VERIFIED and not self.evidence:
            raise ValueError("VERIFIED beliefs require direct evidence")
        if self.status == BeliefStatus.CONTRADICTED and not self.contradictions:
            raise ValueError("CONTRADICTED beliefs require contradictory evidence")
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return self

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "Belief":
        return cls(
            claim=str(obj["claim"]),
            status=BeliefStatus(str(obj.get("status", "UNKNOWN"))),
            confidence=float(obj.get("confidence", 0.0)),
            context=str(obj.get("context", "global")),
            evidence=list(obj.get("evidence") or []),
            contradictions=list(obj.get("contradictions") or []),
            source=obj.get("source"),
            rom_sha256=obj.get("rom_sha256"),
            updated_at=str(obj.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        )


class BeliefLedger:
    def __init__(self, beliefs: Iterable[Belief] | None = None):
        self._items: dict[tuple[str, str], Belief] = {}
        for belief in beliefs or []:
            self.set(belief)

    @staticmethod
    def _key(claim: str, context: str) -> tuple[str, str]:
        return (context.strip().lower(), claim.strip().lower())

    def set(self, belief: Belief) -> Belief:
        belief.normalize()
        self._items[self._key(belief.claim, belief.context)] = belief
        return belief

    def get(self, claim: str, context: str = "global") -> Belief | None:
        return self._items.get(self._key(claim, context))

    def observe(self, claim: str, evidence: str, *, context: str = "global", repeated: int = 1,
                source: str | None = None, rom_sha256: str | None = None,
                direct: bool = True) -> Belief:
        """Add supporting evidence conservatively.

        Direct observation can verify a narrowly phrased claim.  Repeated indirect cues
        can rise to HIGH_CONFIDENCE but never become VERIFIED without direct evidence.
        """
        old = self.get(claim, context)
        ev = list(old.evidence) if old else []
        if evidence not in ev:
            ev.append(evidence)
        if direct:
            status = BeliefStatus.VERIFIED
            conf = 1.0
        else:
            support = max(1, repeated) + len(ev) - 1
            status = BeliefStatus.HIGH_CONFIDENCE if support >= 2 else BeliefStatus.PLAUSIBLE
            conf = min(0.9, 0.45 + 0.15 * support)
        return self.set(Belief(claim, status, conf, context, ev,
                               list(old.contradictions) if old else [], source or (old.source if old else None),
                               rom_sha256 or (old.rom_sha256 if old else None)))

    def hypothesize(self, claim: str, *, context: str = "global", source: str = "heuristic",
                    confidence: float = 0.35, rom_sha256: str | None = None) -> Belief:
        old = self.get(claim, context)
        if old and old.status in {BeliefStatus.VERIFIED, BeliefStatus.HIGH_CONFIDENCE}:
            return old
        return self.set(Belief(claim, BeliefStatus.PLAUSIBLE, min(float(confidence), 0.59), context,
                               list(old.evidence) if old else [], list(old.contradictions) if old else [],
                               source, rom_sha256))

    def contradict(self, claim: str, evidence: str, *, context: str = "global") -> Belief:
        old = self.get(claim, context)
        contradictions = list(old.contradictions) if old else []
        if evidence not in contradictions:
            contradictions.append(evidence)
        return self.set(Belief(claim, BeliefStatus.CONTRADICTED, 0.0, context,
                               list(old.evidence) if old else [], contradictions,
                               old.source if old else None, old.rom_sha256 if old else None))

    def action_confidence(self, claims: Iterable[str], *, context: str = "global") -> float:
        vals = []
        for claim in claims:
            b = self.get(claim, context) or self.get(claim, "global")
            vals.append(STATUS_SCORE[b.status] * max(b.confidence, STATUS_SCORE[b.status]) if b else 0.0)
        return min(vals) if vals else 1.0

    def grouped(self) -> dict[str, list[dict[str, Any]]]:
        out = {s.value: [] for s in BeliefStatus}
        for b in sorted(self._items.values(), key=lambda x: (x.status.value, x.context, x.claim)):
            out[b.status.value].append(b.to_dict())
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "beliefs": [b.to_dict() for b in self._items.values()]}

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "BeliefLedger":
        return cls(Belief.from_dict(x) for x in (obj.get("beliefs") or []))

    @classmethod
    def load(cls, path: str | Path) -> "BeliefLedger":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> str:
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return str(p)
