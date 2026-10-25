
from __future__ import annotations
"""ROMancer v18 cross-engine game model and ontology."""
import json
from collections import Counter
from pathlib import Path
from typing import Any
from .util import write_json

ENGINES={
 'DialogueEngine':['dialogue','text_box','choice','speaker','backlog'],
 'MenuEngine':['menu','focus','confirm','cancel','cursor'],
 'ShopEngine':['shop','buy','sell','price','currency','quantity'],
 'InventoryEngine':['inventory','item','equipment','slot','consume'],
 'BattleEngine':['combat','battle','hp','enemy','command','target','damage'],
 'EventEngine':['event','flag','script','trigger','cutscene'],
 'MapEngine':['map','transition','exit','collision','tile','door'],
 'SaveEngine':['save','load','sram','checkpoint','slot'],
 'EconomyEngine':['currency','reward','shop','cost','farm'],
 'ProgressionEngine':['xp','level','ability','unlock','quest'],
 'GraphicsEngine':['sprite','tile','palette','vram','oam','portrait'],
 'AudioEngine':['music','sfx','pcm','silence','cue']
}
MECHANICS=['currency','HP','MP','level','experience','equipment','status effect','dialogue choice','battle command','shop purchase','save point','map transition','random encounter','boss phase','farming loop','quest flag']

def _load(x: str|dict[str,Any]|list[Any])->Any:
    if isinstance(x,(dict,list)): return x
    return json.loads(Path(x).read_text(encoding='utf-8'))

def architecture_match(observations: str|dict[str,Any]|list[Any], out: str|None=None)->dict[str,Any]:
    data=_load(observations); obs=data.get('observations',data) if isinstance(data,dict) else data
    text=' '.join(json.dumps(o,sort_keys=True).lower() for o in obs)
    matches=[]
    for eng,words in ENGINES.items():
        hits=sum(text.count(w.lower()) for w in words)
        score=min(1.0,hits/max(3,len(words)))
        if hits: matches.append({'engine':eng,'score':round(score,3),'status':'PLAUSIBLE' if score<0.67 else 'HIGH_CONFIDENCE','evidence_terms':[w for w in words if w.lower() in text]})
    matches.sort(key=lambda x:x['score'],reverse=True)
    genre=[]
    engines={m['engine'] for m in matches}
    if {'BattleEngine','MapEngine','DialogueEngine'} <= engines: genre.append({'model':'menu_or_exploration_rpg','status':'PLAUSIBLE'})
    if {'ShopEngine','EconomyEngine'} <= engines: genre.append({'model':'economy_rpg_like','status':'PLAUSIBLE'})
    res={'tool':'ROMancer','version':'18.0.0','feature':'v18 architecture match','observations':len(obs),'matches':matches,'model_hypotheses':genre,'policy':'Engine models are test templates until verified on the exact game.'}
    if out: write_json(out,res)
    return res

def model_game(observations: str|dict[str,Any]|list[Any], out: str|None=None)->dict[str,Any]:
    match=architecture_match(observations)
    confirmed=[m for m in match['matches'] if m['status']=='HIGH_CONFIDENCE']
    candidate=[m for m in match['matches'] if m['status']!='HIGH_CONFIDENCE']
    states=Counter(); resources=Counter()
    data=_load(observations); obs=data.get('observations',data) if isinstance(data,dict) else data
    for o in obs:
        if isinstance(o,dict):
            for key in ('state','from','to'):
                if o.get(key): states[str(o.get(key)).upper()]+=1
            if o.get('resource'): resources[str(o.get('resource'))]+=1
            if str(o.get('kind','')).lower()=='resource': resources[str(o.get('name','unknown'))]+=1
    res={'tool':'ROMancer','version':'18.0.0','feature':'v18 cross-engine game model','confirmed_systems':[x['engine'] for x in confirmed],'candidate_systems':[x['engine'] for x in candidate],'known_states':sorted(states),'resources':sorted(resources),'mechanic_ontology':MECHANICS,'model_hypotheses':match['model_hypotheses'],'policy':'A model summarizes evidence and hypotheses; it does not assert untested mechanics.'}
    if out: write_json(out,res)
    return res

def engine_template(engine: str, out: str|None=None)->dict[str,Any]:
    templates={
        'ShopEngine':['identify currency display','identify focused item','read price/quantity','buy one only from safe state','verify currency decrease','verify inventory increase','cancel without purchase'],
        'DialogueEngine':['detect text box','read continuation cue','advance once','detect next page/choice/end','extract objective if present'],
        'BattleEngine':['identify HP/resources','identify active command state','select safe command','verify target/action/result','record damage/resource costs'],
        'MapEngine':['identify position','test collision safely','identify exits','verify transition destination and return path']}
    steps=templates.get(engine, ['collect observations','derive hypotheses','create reversible tests','verify state transitions'])
    res={'tool':'ROMancer','version':'18.0.0','feature':'v18 engine template','engine':engine,'test_steps':[{'step':s,'status':'template'} for s in steps],'policy':'Templates generate tests; the exact game decides truth.'}
    if out: write_json(out,res)
    return res
