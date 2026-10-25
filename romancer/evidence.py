from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from .util import read_json, write_json


def evidence_path(project: str | Path) -> Path:
    return Path(project) / "evidence" / "evidence.json"


def load_evidence(project: str | Path) -> list[dict]:
    p = evidence_path(project)
    if not p.exists():
        return []
    return read_json(p)


def add_evidence(project: str | Path, claim: str, status: str = "unverified", confidence: float = 0.5, detail: str = "") -> dict:
    items = load_evidence(project)
    item = {
        "id": f"E{len(items)+1:04d}",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "claim": claim,
        "status": status,
        "confidence": confidence,
        "detail": detail,
    }
    items.append(item)
    write_json(evidence_path(project), items)
    return item


def export_ai_bundle(project: str | Path) -> dict:
    from .project import load_project
    return {
        "project": load_project(project),
        "evidence": load_evidence(project),
        "instruction": "Use only the supplied evidence. Separate confirmed facts from hypotheses. Do not invent offsets.",
    }
