from __future__ import annotations

"""ROMancer v15 self-improving knowledge, profile generation, and capability self-evaluation."""

import json, hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from .util import write_json


def _load(obj: str | dict[str, Any] | list[Any]) -> Any:
    if isinstance(obj, str):
        return json.loads(Path(obj).read_text(encoding="utf-8"))
    return obj


def _sha_file(path: str) -> str:
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(65536),b''):
            h.update(chunk)
    return h.hexdigest()


def inherit_knowledge(source: str | dict[str, Any], target: str | dict[str, Any], out: str | None=None) -> dict[str, Any]:
    """Prepare candidate inherited knowledge for a different ROM/project.

    Source facts are not promoted to verified unless target explicitly supplies a
    revalidation result. This preserves the evidence discipline from v9.
    """
    src=_load(source); tgt=_load(target)
    src_hash=(src.get('game') or {}).get('rom_sha256') or src.get('rom_sha256')
    tgt_hash=(tgt.get('game') or {}).get('rom_sha256') or tgt.get('rom_sha256')
    same_hash=bool(src_hash and tgt_hash and src_hash==tgt_hash)
    revalidated=set(tgt.get('revalidated_fact_ids',[]))
    inherited=[]
    for fact in src.get('facts',[]):
        fid=str(fact.get('id') or fact.get('name') or len(inherited))
        status='VERIFIED' if same_hash or fid in revalidated else 'INHERITED_CANDIDATE'
        inherited.append({
            'id':fid,
            'claim':fact.get('claim') or fact.get('name'),
            'domain':fact.get('domain','unknown'),
            'source_status':fact.get('status','UNKNOWN'),
            'target_status':status,
            'source_rom_sha256':src_hash,
            'target_rom_sha256':tgt_hash,
            'evidence_required':None if status=='VERIFIED' else 'Revalidate on the target ROM/hash before treating as game-specific fact.'
        })
    result={
        'tool':'ROMancer',
        'feature':'v15 knowledge inheritance',
        'source_game':src.get('game',{}),
        'target_game':tgt.get('game',{}),
        'same_rom_hash':same_hash,
        'inherited_count':len(inherited),
        'verified_for_target_count':sum(1 for x in inherited if x['target_status']=='VERIFIED'),
        'candidate_for_target_count':sum(1 for x in inherited if x['target_status']!='VERIFIED'),
        'facts':inherited,
        'policy':'Cross-project knowledge is inherited as candidate unless the ROM hash is identical or explicit target revalidation is supplied.'
    }
    if out: write_json(out,result)
    return result


def generate_profile(observations: str | dict[str, Any] | list[dict[str, Any]], out: str | None=None) -> dict[str, Any]:
    """Generate a conservative game profile from observations.

    Observations are structured events such as:
    {"kind":"control","state":"exploration","input":"A","semantic":"interact","status":"VERIFIED"}
    {"kind":"state_transition","from":"EXPLORATION","to":"DIALOGUE","status":"VERIFIED"}
    """
    obs=_load(observations)
    if isinstance(obs,dict): obs=obs.get('observations',[])
    controls=defaultdict(dict); transitions=[]; resources=Counter(); save_systems=set(); movement=[]; objective_sources=Counter(); states=Counter(); confidence=Counter()
    for o in obs:
        status=str(o.get('status','UNKNOWN')).upper(); confidence[status]+=1
        kind=str(o.get('kind','')).lower()
        if kind=='control':
            st=str(o.get('state','unknown')).lower(); sem=str(o.get('semantic','unknown'))
            controls[st][sem]={'input':o.get('input'), 'status':status, 'evidence':o.get('evidence')}
        elif kind=='state_transition':
            transitions.append({'from':o.get('from'), 'to':o.get('to'), 'trigger':o.get('trigger'), 'status':status})
            if o.get('from'): states[str(o.get('from')).upper()]+=1
            if o.get('to'): states[str(o.get('to')).upper()]+=1
        elif kind=='resource':
            resources[str(o.get('name','unknown'))]+=1
        elif kind=='save_system':
            save_systems.add(str(o.get('system','unknown')))
        elif kind=='movement':
            movement.append({'model':o.get('model'), 'directions':o.get('directions'), 'status':status})
        elif kind=='objective_source':
            objective_sources[str(o.get('source','unknown'))]+=1
    # Genre inference remains a candidate based on observed traits.
    genre_scores=Counter()
    if 'EXPLORATION' in states and 'COMBAT' in states and resources.get('HP'): genre_scores['rpg_like']+=2
    if any(m.get('model') in ('4-direction','8-direction','tile') for m in movement): genre_scores['top_down_or_tile']+=1
    if 'DIALOGUE' in states: genre_scores['narrative_or_rpg']+=1
    if 'SHOP' in states or resources.get('currency'): genre_scores['economy_rpg_like']+=1
    profile={
        'tool':'ROMancer',
        'feature':'v15 automatic profile generation',
        'profile':{
            'controls':dict(controls),
            'known_states':sorted(states.keys()),
            'state_transitions':transitions,
            'movement_models':movement,
            'resources':sorted(resources.keys()),
            'save_systems':sorted(save_systems),
            'objective_sources':dict(objective_sources),
            'genre_hypotheses':[{'genre':g,'score':s,'status':'PLAUSIBLE'} for g,s in genre_scores.most_common()]
        },
        'observation_count':len(obs),
        'confidence_counts':dict(confidence),
        'policy':'Generated profile records observations and hypotheses. It does not convert unverified convention into fact.'
    }
    if out: write_json(out,profile)
    return profile


def self_evaluate(manifest: str | dict[str, Any], out: str | None=None) -> dict[str, Any]:
    """Evaluate whether ROMancer should proceed, ask for evidence, or block autonomy."""
    m=_load(manifest)
    blockers=[]; warnings=[]; ready=[]
    for req in m.get('required_capabilities',[]):
        if not req.get('available',False): blockers.append({'type':'missing_capability','name':req.get('name'),'reason':req.get('reason','capability unavailable')})
        else: ready.append({'type':'capability','name':req.get('name')})
    for fact in m.get('required_facts',[]):
        status=str(fact.get('status','UNKNOWN')).upper()
        if status not in ('VERIFIED','HIGH_CONFIDENCE'):
            blockers.append({'type':'insufficient_evidence','id':fact.get('id'), 'claim':fact.get('claim'), 'status':status})
        elif status=='HIGH_CONFIDENCE':
            warnings.append({'type':'not_fully_verified','id':fact.get('id'), 'claim':fact.get('claim')})
        else:
            ready.append({'type':'fact','id':fact.get('id')})
    for risk in m.get('risks',[]):
        if risk.get('severity') in ('critical','high') and not risk.get('mitigation_verified'):
            blockers.append({'type':'unmitigated_risk','name':risk.get('name'), 'severity':risk.get('severity')})
    mode='PROCEED' if not blockers else 'BLOCK_AUTONOMOUS_ACTION'
    result={'tool':'ROMancer','feature':'v15 self-evaluation','mode':mode,'blocker_count':len(blockers),'warning_count':len(warnings),'ready_count':len(ready),'blockers':blockers,'warnings':warnings,'ready':ready,
            'policy':'Autonomy is blocked when required evidence/capability is missing. Human review can still use the report.'}
    if out: write_json(out,result)
    return result


def knowledge_vault(root: str, out: str | None=None) -> dict[str, Any]:
    """Index portable JSON knowledge without copying ROM/content bytes."""
    rootp=Path(root); entries=[]; skipped=[]
    forbidden={'.sfc','.smc','.nes','.gba','.gb','.gbc','.gen','.md','.bin','.iso','.chd','.srm','.sav','.state'}
    for p in rootp.rglob('*'):
        if not p.is_file(): continue
        if p.suffix.lower() in forbidden:
            skipped.append(str(p.relative_to(rootp))); continue
        if p.suffix.lower()=='.json':
            try:
                data=json.loads(p.read_text(encoding='utf-8'))
                entries.append({'path':str(p.relative_to(rootp)), 'sha256':_sha_file(str(p)), 'tool':data.get('tool'), 'feature':data.get('feature'), 'game':data.get('game') or (data.get('profile') or {}).get('game')})
            except Exception as e:
                entries.append({'path':str(p.relative_to(rootp)), 'error':str(e)})
    result={'tool':'ROMancer','feature':'v15 knowledge vault index','root':str(rootp),'entry_count':len(entries),'entries':entries,'skipped_content_count':len(skipped),'skipped_content_examples':skipped[:50],
            'policy':'Vault indexes portable knowledge and deliberately skips ROM, disc, save and runtime-content suffixes.'}
    if out: write_json(out,result)
    return result


def platform_sdk_check(manifest: str | dict[str, Any], out: str | None=None) -> dict[str, Any]:
    m=_load(manifest)
    required=['identity','address_translation','memory_regions','input','graphics','audio','debug_adapter','assembler','disassembler']
    modules=m.get('modules',{})
    rows=[]; ok=True
    for name in required:
        status=str(modules.get(name,'missing')).lower()
        present=status in ('ok','available','implemented','partial')
        if status in ('missing','unavailable','unknown'): ok=False
        rows.append({'module':name,'status':status,'present':present})
    result={'tool':'ROMancer','feature':'v15 platform SDK contract','platform':m.get('platform'),'ok':ok,'modules':rows,
            'policy':'A platform pack is modular; missing contracts are reported instead of guessed.'}
    if out: write_json(out,result)
    return result


def project_plan(request: str, out: str | None=None) -> dict[str, Any]:
    text=Path(request).read_text(encoding='utf-8') if Path(str(request)).exists() else str(request)
    lower=text.lower()
    tasks=[]
    def add(name, evidence, autonomous='candidate'):
        tasks.append({'task':name,'evidence_required':evidence,'autonomy':autonomous})
    add('Identify source ROM, region, version and hash','exact ROM identity and supported platform','required')
    add('Create baseline runtime scenario','boot/play evidence and reproducible starting state','required')
    if any(w in lower for w in ['command','skill','ability','spell','mockery']):
        add('Locate command/ability table and dispatcher','verified table/provenance or debugger trace')
        add('Design mechanic semantics','explicit target effect, duration, immunity/stacking rules')
        add('Implement lowest-risk data or handler change','patch ownership + causal verification')
    if any(w in lower for w in ['portrait','sprite','graphics','animation']):
        add('Trace graphics provenance','asset -> decode -> VRAM/OAM/tilemap/palette evidence')
    if any(w in lower for w in ['dialogue','story','npc','quest']):
        add('Map dialogue/objective triggers','runtime dialogue IDs and event flags')
    add('Generate bounded candidate repair/implementation','temporary build and explicit oracle','candidate')
    add('Replay focused regression','original repro and intended feature tests','required')
    add('Run release certification gates','static, runtime, coverage and historical regressions','required')
    result={'tool':'ROMancer','feature':'v15 autonomous project planning','request':text,'task_count':len(tasks),'tasks':tasks,
            'policy':'Plan decomposes the request into verifiable engineering steps; unsupported steps remain blocked until evidence exists.'}
    if out: write_json(out,result)
    return result
