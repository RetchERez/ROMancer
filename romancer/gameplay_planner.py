from __future__ import annotations

"""Risk-aware action selection for ROMancer v9."""

from dataclasses import dataclass, asdict, field
from typing import Any
from .gameplay_beliefs import BeliefLedger

DESTRUCTIVE_KINDS={"delete","discard","sell","overwrite","abandon","permanent_spend","rare_currency_spend","irreversible_continue"}

@dataclass
class CandidateAction:
    name:str
    kind:str="act"
    context:str="global"
    progress_value:float=0.0
    information_gain:float=0.0
    survival_value:float=0.0
    reversibility:float=1.0
    failure_risk:float=0.0
    resource_cost:float=0.0
    required_claims:list[str]=field(default_factory=list)
    metadata:dict[str,Any]=field(default_factory=dict)


def score_action(a:CandidateAction, ledger:BeliefLedger, *, mode:str="player", uncertainty:float=0.5)->dict[str,Any]:
    conf=ledger.action_confidence(a.required_claims,context=a.context)
    destructive=a.kind in DESTRUCTIVE_KINDS
    guard_ok=bool(a.metadata.get("target_verified") and a.metadata.get("cost_verified") and a.metadata.get("permanence_verified"))
    blocked=destructive and not guard_ok
    # Unknown states favor information and reversibility. QA mode values evidence more; player mode values progress/survival more.
    if mode=="qa":
        value=2.2*a.information_gain+1.0*a.progress_value+1.2*a.survival_value
    elif mode in {"explore","blind"}:
        value=2.0*a.information_gain+0.8*a.progress_value+1.0*a.survival_value
    else:
        value=1.1*a.information_gain+1.8*a.progress_value+1.6*a.survival_value
    risk=(1.8*a.failure_risk+1.0*a.resource_cost+(1-a.reversibility)*(1.5+2.5*uncertainty))
    confidence_penalty=(1-conf)*(0.5+2.5*uncertainty) if a.required_claims else 0.0
    score=value-risk-confidence_penalty
    if blocked: score=-1e9
    return {"name":a.name,"kind":a.kind,"score":round(score,6),"blocked":blocked,"destructive_guard_ok":guard_ok,
            "action_confidence":round(conf,4),"value":round(value,4),"risk":round(risk,4),"confidence_penalty":round(confidence_penalty,4),
            "metadata":a.metadata}


def choose_action(actions:list[CandidateAction], ledger:BeliefLedger, *, mode:str="player", uncertainty:float=0.5)->dict[str,Any]:
    scored=[score_action(a,ledger,mode=mode,uncertainty=uncertainty) for a in actions]
    scored.sort(key=lambda x:(-x["score"],x["name"]))
    selected=next((x for x in scored if not x["blocked"]),None)
    return {"mode":mode,"uncertainty":uncertainty,"selected":selected,"ranking":scored,
            "principle":"When confidence is low, favor reversible information-gathering actions before irreversible commitment."}
