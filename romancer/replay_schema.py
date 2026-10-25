"""Declarative routes: inputs, measured assertions and explicitly named transitions."""
import json
import re
from .asset_schema import fields,label,number
from .script_schema import canonical_bytes
from .runtime_session import validate_steps


def validate_route(route:dict)->dict:
    route=json.loads(canonical_bytes(route,max_bytes=1024**2))
    fields(route,'schema_version id max_frames max_actions steps');number(route['schema_version'],1,1);label(route['id'])
    number(route['max_frames'],1,6000);number(route['max_actions'],1,100)
    if type(route['steps']) is not list or not 1<=len(route['steps'])<=route['max_actions']:raise ValueError('route action budget exceeded')
    simple=[];assertions=0;checkpoints=0
    for step in route['steps']:
        fields(step,'frames buttons port assertions transition checkpoint')
        simple.append({key:step[key] for key in ('frames','buttons','port')})
        if type(step['assertions']) is not list or len(step['assertions'])>32:raise ValueError('invalid assertion list')
        assertions+=len(step['assertions'])
        if type(step['checkpoint']) is not bool:raise ValueError('checkpoint must be boolean')
        checkpoints+=step['checkpoint']
        for assertion in step['assertions']:
            if assertion.get('kind')=='memory_eq':
                fields(assertion,'kind region offset expected_hex');number(assertion['region'],0,3);number(assertion['offset'],0,256*1024**2)
                if type(assertion['expected_hex']) is not str or not re.fullmatch('(?:[0-9a-f]{2}){1,4096}',assertion['expected_hex']):raise ValueError('invalid expected memory bytes')
            elif assertion.get('kind')=='capture_sha256':
                fields(assertion,'kind sha256')
                if type(assertion['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',assertion['sha256']):raise ValueError('invalid capture hash')
            elif assertion.get('kind')=='frame_region':
                from .visual_checks import validate_assertion
                validate_assertion(assertion)
            else:raise ValueError('unsupported route assertion')
        if step['transition'] is not None:
            fields(step['transition'],'from to objective')
            for value in step['transition'].values():label(value)
            if not step['assertions']:raise ValueError('a named transition needs a measured assertion')
    validate_steps(simple)
    if not assertions:raise ValueError('a measured route requires at least one explicit assertion')
    if sum(s['frames'] for s in simple)>route['max_frames'] or assertions>256 or checkpoints>4:raise ValueError('route aggregate budget exceeded')
    return route
