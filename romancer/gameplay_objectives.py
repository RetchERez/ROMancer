from __future__ import annotations

"""Conservative objective compilation for ROMancer v9.

Free-form text extraction intentionally produces candidate objectives.  Exact UI fields,
quest-log fields, authored profiles, or runtime event evidence can mark an objective as
verified separately.
"""

from typing import Any
import re
from .gameplay_state import ObjectiveRecord

VERBS = {
    "reach","go","travel","enter","leave","escape","defeat","kill","beat","survive","talk",
    "speak","deliver","give","collect","find","obtain","get","activate","use","open","protect",
    "defend","escort","capture","investigate","return","bring","meet"
}
VERB_NORMALIZE = {"go":"reach","travel":"reach","kill":"defeat","beat":"defeat","speak":"talk",
                  "get":"obtain","bring":"deliver","meet":"talk"}


def compile_structured_objective(obj: dict[str, Any], *, source: str="structured") -> ObjectiveRecord:
    verb = obj.get("verb")
    if verb:
        verb=VERB_NORMALIZE.get(str(verb).lower(),str(verb).lower())
    return ObjectiveRecord(
        verb=verb,target=obj.get("target"),destination=obj.get("where") or obj.get("destination"),
        condition=obj.get("condition"),deadline=obj.get("deadline"),
        completion_signal=obj.get("completion_signal"),source=source,
        confidence=str("VERIFIED" if obj.get("verified") else (obj.get("confidence") or "HIGH_CONFIDENCE"))
    )


def extract_candidate_objective(text: str, *, source: str="dialogue") -> dict[str, Any]:
    clean=" ".join(text.strip().split())
    low=clean.lower()
    take_to=re.search(r"\btake\s+(.+?)\s+to\s+([^,.;]+)",clean,re.I)
    if take_to:
        target=take_to.group(1).strip(); destination=take_to.group(2).strip()
        dead_m=re.search(r"\b(before|within|by)\s+([^,.;]+)",destination,re.I)
        deadline=None
        if dead_m:
            deadline=(dead_m.group(1)+" "+dead_m.group(2)).strip()
            destination=destination[:dead_m.start()].strip()
        obj=ObjectiveRecord(verb="deliver",target=target,destination=destination,deadline=deadline,source=source,confidence="PLAUSIBLE")
        return {"objective":obj.__dict__,"status":"PLAUSIBLE","reason":"Imperative delivery pattern inferred from free-form text; verify against the exact game's dialogue/objective state."}
    match=None
    for verb in sorted(VERBS,key=len,reverse=True):
        m=re.search(rf"\b{re.escape(verb)}\b",low)
        if m and (match is None or m.start()<match[0]): match=(m.start(),m.end(),verb)
    if not match:
        return {"objective":ObjectiveRecord(source=source,confidence="UNKNOWN").__dict__,
                "status":"UNKNOWN","reason":"No supported objective verb was found; do not guess an objective."}
    _,end,verb=match
    normalized=VERB_NORMALIZE.get(verb,verb)
    tail=clean[end:].strip(" :,-.!?")
    destination=None; target=tail or None; deadline=None
    # Limited cue extraction, deliberately candidate-only.
    dest_m=re.search(r"\b(?:at|in|to|into|toward|towards)\s+([^,.;]+)",tail,re.I)
    if dest_m: destination=dest_m.group(1).strip()
    dead_m=re.search(r"\b(before|within|by)\s+([^,.;]+)",tail,re.I)
    if dead_m: deadline=(dead_m.group(1)+" "+dead_m.group(2)).strip()
    obj=ObjectiveRecord(verb=normalized,target=target,destination=destination,deadline=deadline,
                        source=source,confidence="PLAUSIBLE")
    return {"objective":obj.__dict__,"status":"PLAUSIBLE",
            "reason":"Extracted from free-form text as a hypothesis. Verify against the exact game's UI, dialogue state, quest log, or runtime behavior."}


def objective_information_gaps(obj: ObjectiveRecord) -> list[str]:
    gaps=[]
    if not obj.verb: gaps.append("verb")
    if not obj.target and obj.verb not in {"survive","escape","leave"}: gaps.append("target")
    if obj.confidence not in {"VERIFIED","HIGH_CONFIDENCE"}: gaps.append("verification")
    if not obj.completion_signal: gaps.append("completion_signal")
    return gaps
