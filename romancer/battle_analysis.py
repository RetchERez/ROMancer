"""Bounded recommendations under declared costs/ranges, not inferred game rules."""
from fractions import Fraction
from .asset_schema import fields,label,number
from .runtime_session import snapshot_json


def analyze_battle(profile:dict,observations:list[dict],budget:dict)->dict:
    profile=snapshot_json(profile);observations=snapshot_json(observations);budget=snapshot_json(budget)
    fields(profile,'schema_version id semantics actions');number(profile['schema_version'],1,1);label(profile['id'])
    if profile['semantics']!='declared-action-cost-v1':raise ValueError('unsupported battle semantics')
    fields(budget,'retries_used max_retries failures_used max_failures')
    for value in budget.values():number(value,0,100)
    if type(profile['actions']) is not list or not 1<=len(profile['actions'])<=128:raise ValueError('invalid action count')
    ids=set()
    for action in profile['actions']:
        fields(action,'id label min_range max_range cost power accuracy_per_mille');label(action['id']);label(action['label'])
        if action['id'] in ids:raise ValueError('duplicate action')
        ids.add(action['id']);number(action['min_range'],0,10000);number(action['max_range'],action['min_range'],10000)
        number(action['power'],0,1000000);number(action['accuracy_per_mille'],0,1000)
        if type(action['cost']) is not dict or len(action['cost'])>32:raise ValueError('invalid resource costs')
        for key,value in action['cost'].items():label(key);number(value,0,1000000)
    if type(observations) is not list or len(observations)>16:raise ValueError('too many battle observations')
    resources={};distance=None;bonuses={};seen=set()
    for item in observations:
        kind=item.get('kind')
        if kind in seen:raise ValueError('ambiguous duplicated battle observation')
        seen.add(kind)
        if kind=='range':fields(item,'kind value');distance=number(item['value'],0,10000)
        elif kind in ('resources','equipment'):
            key='values' if kind=='resources' else 'bonuses';fields(item,'kind '+key)
            values=item[key]
            if type(values) is not dict or len(values)>128:raise ValueError('invalid battle observation')
            for name,value in values.items():label(name);number(value,0,1000000)
            if kind=='resources':resources=values
            else:bonuses=values
        else:raise ValueError('unsupported battle observation')
    result={'schema_version':1,'operation':'battle-analysis','ok':True,'status':'ANALYZED',
            'scope':'declared_model_recommendation','recommended_action':None,'actions':[],
            'assumptions':['Ranges, equipment bonuses, power, accuracy, and costs are supplied model assumptions.',
                           'This analysis does not measure an emulator or prove a battle outcome.'],'budget':budget}
    if budget['retries_used']>=budget['max_retries'] or budget['failures_used']>=budget['max_failures']:
        result.update(status='STOP',reason='Retry or failure budget exhausted');return result
    if distance is None:result.update(status='UNRESOLVED',reason='A measured or declared range is required');return result
    ranked=[]
    for action in profile['actions']:
        reasons=[]
        if not action['min_range']<=distance<=action['max_range']:reasons.append('out of declared range')
        if any(resources.get(key,-1)<value for key,value in action['cost'].items()):reasons.append('insufficient or unknown resources')
        expected=Fraction((action['power']+bonuses.get(action['id'],0))*action['accuracy_per_mille'],1000)
        row={'id':action['id'],'label':action['label'],'eligible':not reasons,'reasons':reasons,
             'expected_power':{'numerator':expected.numerator,'denominator':expected.denominator},'cost':action['cost']}
        result['actions'].append(row)
        if not reasons:ranked.append((expected,-sum(action['cost'].values()),action['id']))
    ranked.sort(reverse=True)
    if ranked:result['recommended_action']=ranked[0][2]
    else:result.update(status='STOP',reason='No action satisfies the declared constraints')
    result['ordering']=[item[2] for item in ranked];return result
