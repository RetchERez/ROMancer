from __future__ import annotations

"""Failure classification and response policy for ROMancer v9."""

from typing import Any

CATEGORIES = ["EXECUTION","KNOWLEDGE","PREPARATION","STRATEGY","PROGRESSION","PUZZLE","NAVIGATION","STATE","RANDOM","BUG","UNKNOWN"]
RESPONSES = {
    "EXECUTION":"practice the specific timing, movement, aim, or input sequence",
    "KNOWLEDGE":"observe, read, and run a controlled mechanic test",
    "PREPARATION":"heal, restock, equip, or restore required resources",
    "STRATEGY":"change positioning, target priority, action order, or resource allocation",
    "PROGRESSION":"upgrade or farm only the verified progression shortfall",
    "PUZZLE":"model puzzle state and change one variable at a time",
    "NAVIGATION":"reorient from the map, objective, landmark, or last confirmed junction",
    "STATE":"resolve the current dialogue, menu, turn, loading, or scripted event state",
    "RANDOM":"retry only if the expected strategy remains sound; collect more trials before changing the rule model",
    "BUG":"reproduce, preserve exact state, record expected versus actual, and hand evidence to causal debugging",
    "UNKNOWN":"gather information before committing to a remedy",
}


def classify_failure(obs: dict[str, Any]) -> dict[str, Any]:
    """Classify from explicit evidence fields without inventing missing facts."""
    scores={k:0 for k in CATEGORIES}
    reasons={k:[] for k in CATEGORIES}
    def add(cat,pts,why): scores[cat]+=pts; reasons[cat].append(why)

    if obs.get("technical_exception") or obs.get("crash"):
        add("BUG",8,"runtime crash/technical exception observed")
    if obs.get("verified_expected_state") and obs.get("reproduced") and obs.get("actual_contradicts_expected"):
        add("BUG",8,"verified expected behavior is reproducibly contradicted")
    if obs.get("waiting_dialogue") or obs.get("waiting_menu") or obs.get("waiting_turn") or obs.get("scripted_control_lock"):
        add("STATE",6,"active interface/event state can explain lack of progression")
    if obs.get("wrong_route") or obs.get("lost") or obs.get("unreachable_marker"):
        add("NAVIGATION",5,"route/location evidence indicates navigation problem")
    if obs.get("puzzle_active") or obs.get("puzzle_rule_unknown"):
        add("PUZZLE",5,"active puzzle or unknown puzzle rule")
    if obs.get("avoidable_damage") or obs.get("missed_timing") or obs.get("missed_jump") or obs.get("aim_error"):
        add("EXECUTION",5,"failure linked to controllable execution")
    if obs.get("mechanic_unknown") or obs.get("objective_unknown") or obs.get("enemy_pattern_unknown"):
        add("KNOWLEDGE",5,"required mechanic/objective/enemy behavior is not understood")
    if obs.get("low_starting_health") or obs.get("out_of_ammo") or obs.get("missing_healing") or obs.get("equipment_not_equipped"):
        add("PREPARATION",5,"known preparation deficit")
    if obs.get("bad_positioning") or obs.get("wrong_target_priority") or obs.get("poor_action_order") or obs.get("resource_waste"):
        add("STRATEGY",5,"strategy/positioning evidence")
    if obs.get("verified_underpowered") or obs.get("required_level_shortfall") or obs.get("required_upgrade_shortfall"):
        add("PROGRESSION",5,"verified permanent progression shortfall")
    if obs.get("probabilistic_action") and not obs.get("rule_contradicted"):
        add("RANDOM",3,"known probabilistic action can fail without invalidating strategy")

    ranked=sorted(scores.items(), key=lambda kv:(-kv[1],kv[0]))
    cat,score=ranked[0]
    if score<=0: cat="UNKNOWN"
    repeated=int(obs.get("same_cause_failures") or 0)
    adaptation = repeated >= 3 and cat not in {"RANDOM","UNKNOWN"}
    return {
        "category":cat,"score":score,"response":RESPONSES[cat],"reasons":reasons[cat],
        "adapt_strategy":adaptation,
        "repeat_note":"Three or more failures from the same identified cause justify changing method." if adaptation else "Do not overreact to one failure; gather additional evidence where randomness or uncertainty exists.",
        "all_scores":scores,
    }
