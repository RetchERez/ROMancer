from __future__ import annotations

"""Game profile schema and semantic-input resolver for ROMancer v7."""

import copy
import json
from pathlib import Path
from typing import Any

from .rom_ident import identify_rom
from .util import write_json

SCHEMA_VERSION = 1


def builtin_profile_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "profiles"


def list_profiles() -> list[dict[str, Any]]:
    out = []
    for p in sorted(builtin_profile_dir().glob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            out.append({"name": obj.get("name", p.stem), "id": obj.get("id", p.stem), "path": str(p), "system": obj.get("system"), "game": obj.get("game")})
        except Exception as exc:
            out.append({"name": p.stem, "path": str(p), "error": str(exc)})
    return out


def load_profile(name_or_path: str | Path) -> dict[str, Any]:
    p = Path(name_or_path)
    if not p.is_file():
        candidate = builtin_profile_dir() / f"{name_or_path}.json"
        if candidate.is_file():
            p = candidate
        else:
            # also match profile id inside JSON
            for entry in builtin_profile_dir().glob("*.json"):
                try:
                    obj = json.loads(entry.read_text(encoding="utf-8"))
                    if str(obj.get("id", "")).lower() == str(name_or_path).lower():
                        return obj
                except Exception:
                    continue
            raise FileNotFoundError(name_or_path)
    return json.loads(p.read_text(encoding="utf-8"))


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    issues = []
    if profile.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    if not profile.get("id"):
        issues.append("missing id")
    if not profile.get("system"):
        issues.append("missing system")
    controls = profile.get("controls", {})
    if not isinstance(controls, dict):
        issues.append("controls must be an object")
    else:
        for context, mapping in controls.items():
            if not isinstance(mapping, dict):
                issues.append(f"controls.{context} must be an object")
                continue
            for intent, buttons in mapping.items():
                if not isinstance(buttons, list) or not all(isinstance(x, str) for x in buttons):
                    issues.append(f"controls.{context}.{intent} must be a string array")
    for field in profile.get("memory_fields", []):
        if field.get("status") not in {"candidate", "verified"}:
            issues.append(f"memory field {field.get('name')} must have candidate/verified status")
        if field.get("status") == "verified" and not field.get("evidence"):
            issues.append(f"verified memory field {field.get('name')} lacks evidence")
    return {"ok": not issues, "issues": issues, "id": profile.get("id"), "schema_version": profile.get("schema_version")}


def create_profile(rom: str | Path, out: str | Path, *, profile_id: str | None = None, game: str | None = None, genre: str = "unknown") -> dict[str, Any]:
    ident = identify_rom(rom)
    pid = profile_id or Path(rom).stem.lower().replace(" ", "_")
    profile = {
        "schema_version": SCHEMA_VERSION,
        "id": pid,
        "name": game or Path(rom).stem,
        "game": game or Path(rom).stem,
        "system": ident.get("system"),
        "genre": genre,
        "identity": {"sha256": ident.get("sha256"), "crc32": ident.get("crc32"), "size_bytes": ident.get("size_bytes")},
        "runtime": {"preferred_cores": [], "boot_frames": 120, "notes": []},
        "contexts": ["unknown"],
        "controls": {"unknown": {}},
        "memory_fields": [],
        "state_signatures": [],
        "scenarios": [],
        "evidence_policy": "Semantic controls, memory fields, and state labels should be marked verified only when backed by a manual, debugger/runtime evidence, or another cited source.",
    }
    write_json(out, profile)
    return profile


def resolve_intent(profile: dict[str, Any], intent: str, context: str = "field") -> list[str]:
    controls = profile.get("controls", {})
    mapping = controls.get(context, {})
    if intent in mapping:
        return list(mapping[intent])
    # explicit fallback context for shared menu conventions
    mapping = controls.get("global", {})
    if intent in mapping:
        return list(mapping[intent])
    raise KeyError(f"Profile {profile.get('id')} has no verified mapping for intent={intent!r} context={context!r}")


def compile_scenario(scenario: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Resolve semantic `intent` fields to concrete libretro buttons."""
    compiled = copy.deepcopy(scenario)
    default_context = str(compiled.get("context", "field"))
    for step in compiled.get("steps", []):
        if not isinstance(step, dict):
            continue
        context = str(step.get("context", default_context))
        if step.get("intent") and not step.get("button") and not step.get("buttons"):
            step["buttons"] = resolve_intent(profile, str(step["intent"]), context)
            step["resolved_from_intent"] = step["intent"]
        if step.get("intents") and not step.get("candidates"):
            step["candidates"] = [resolve_intent(profile, str(intent), context) for intent in step["intents"]]
            step["resolved_from_intents"] = step["intents"]
    compiled["compiled_profile"] = profile.get("id")
    return compiled
