from __future__ import annotations

"""Resource, purchase, and farming economics for ROMancer v9."""

from dataclasses import dataclass, field
from math import ceil
from typing import Any


@dataclass
class ResourceLedger:
    current: dict[str,float] = field(default_factory=dict)
    targets: dict[str,float] = field(default_factory=dict)
    reserves: dict[str,float] = field(default_factory=dict)

    def shortfall(self,name:str)->float:
        return max(0.0,float(self.targets.get(name,0))+float(self.reserves.get(name,0))-float(self.current.get(name,0)))
    def report(self)->dict[str,Any]:
        names=sorted(set(self.current)|set(self.targets)|set(self.reserves))
        return {"resources":[{"name":n,"current":self.current.get(n,0),"target":self.targets.get(n,0),"reserve":self.reserves.get(n,0),"shortfall":self.shortfall(n)} for n in names]}


def farm_route_metrics(route: dict[str,Any], *, shortfall: float | None=None) -> dict[str,Any]:
    time=max(float(route.get("minutes",route.get("time_minutes",0)) or 0),1e-9)
    gross=float(route.get("gross_reward",route.get("reward",0)) or 0)
    costs=sum(float(route.get(k,0) or 0) for k in ["healing_cost","ammo_cost","repair_cost","travel_cost","entry_cost","consumable_cost"])
    net=gross-costs
    success=max(0.0,min(1.0,float(route.get("success_rate",1.0))))
    failure_cost=float(route.get("failure_cost",0) or 0)
    expected=success*net-(1-success)*failure_cost
    per_min=expected/time
    runs=None
    if shortfall is not None and shortfall>0 and expected>0:
        runs=ceil(shortfall/expected)
    return {"name":route.get("name"),"gross":gross,"costs":costs,"net_success":net,
            "success_rate":success,"failure_cost":failure_cost,"expected_net":round(expected,6),
            "expected_net_per_minute":round(per_min,6),"estimated_successful_equivalent_runs":runs,
            "renewable":bool(route.get("renewable",False))}


def choose_farm(routes:list[dict[str,Any]], *, shortfall:float, progression_likely_to_cover:bool=False) -> dict[str,Any]:
    if shortfall<=0:
        return {"farm":False,"reason":"No defined shortfall remains.","routes":[]}
    if progression_likely_to_cover:
        return {"farm":False,"reason":"Normal progression is expected to cover the shortfall; progress before farming.","routes":[]}
    metrics=[farm_route_metrics(r,shortfall=shortfall) for r in routes]
    valid=[m for m in metrics if m["renewable"] and m["expected_net"]>0]
    valid.sort(key=lambda x:x["expected_net_per_minute"],reverse=True)
    return {"farm":bool(valid),"reason":"Selected highest measured positive risk-adjusted renewable route." if valid else "No verified renewable positive-value route is available.",
            "selected":valid[0] if valid else None,"routes":metrics,"stop_condition":{"shortfall":shortfall,"rule":"stop when target plus reserve is reached"}}


def evaluate_purchase(item:dict[str,Any], *, current_currency:float, reserve:float=0, bottleneck:str|None=None) -> dict[str,Any]:
    cost=float(item.get("cost",0) or 0); remaining=current_currency-cost
    flags=[]
    if item.get("required_progression"): tier=1
    elif item.get("solves_survival_bottleneck"): tier=2
    elif item.get("permanent_upgrade"): tier=3
    elif item.get("reusable_utility"): tier=4
    elif item.get("convenience"): tier=5
    else: tier=6
    if remaining<reserve: flags.append("would_breach_reserve")
    if item.get("unique") and item.get("sell_action"): flags.append("unique_item_sale_requires_guard")
    if item.get("free_copy_known_soon"): flags.append("known_free_copy_available_soon")
    if item.get("already_owned"): flags.append("already_owned")
    useful=not any(x in flags for x in ["would_breach_reserve","already_owned"]) and not item.get("usefulness_unknown",False)
    if bottleneck and item.get("addresses_bottleneck") not in (None,bottleneck): flags.append("does_not_address_current_bottleneck")
    if "does_not_address_current_bottleneck" in flags and tier>1: useful=False
    return {"tier":tier,"affordable":cost<=current_currency,"remaining_currency":remaining,"reserve":reserve,
            "recommend_buy":bool(cost<=current_currency and useful and remaining>=reserve),"flags":flags}
