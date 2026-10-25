"""Player-facing exports use only selected prose; engineering metadata is excluded."""
from html import escape
from .asset_schema import label
from .runtime_session import snapshot_json


def default_credits()->str:return 'By RetchEWretched'


def _text(value,limit=16384):
    if type(value) is not str or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('invalid export text')
    return value


def script_document(model:dict,title:str)->dict:
    """Keep decoded text and declared controls in their original token order."""
    lines=[]
    for record in model['records']:
        tokens=[]
        for token in record['tokens']:
            if token['kind']=='text':tokens.append({'kind':'text','text':''.join(g['text'] for g in token['glyphs'])})
            elif token['kind']=='control':
                role=token.get('layout_role')
                tokens.append({'kind':{'line':'line_break','page':'page_break','pause':'pause'}.get(role,'unknown_control')})
            elif token['kind'] not in ('terminator','padding'):tokens.append({'kind':'text','text':'[Uninterpreted text]'})
        lines.append({'speaker':record.get('annotations',{}).get('speaker_label'),'tokens':tokens})
    return {'title':title,'lines':lines}


def export_script(document:dict,format:str)->str:
    document=snapshot_json(document)
    if format not in ('text','html'):raise ValueError('export format must be text or html')
    title=_text(document['title'],256);lines=document['lines']
    if type(lines) is not list or len(lines)>4096:raise ValueError('script export line budget exceeded')
    content=[]
    for line in lines:
        speaker=_text(line.get('speaker') or 'Unknown speaker',128)
        if 'tokens' in line:
            tokens=line['tokens']
            if type(tokens) is not list or len(tokens)>4096:raise ValueError('script token budget exceeded')
            text='';html=''
            for token in tokens:
                kind=token.get('kind')
                if kind=='text':
                    value=_text(token['text']);text+=value;html+=escape(value).replace('\n','<br>')
                elif kind=='line_break':text+='\n';html+='<br>'
                elif kind=='page_break':text+='\n\n';html+='</p><hr><p>'
                elif kind=='pause':pass
                elif kind=='unknown_control':text+='[Uninterpreted control]';html+='[Uninterpreted control]'
                else:raise ValueError('unknown export token')
            _text(text);content.append((speaker,text,html,False));continue
        text=_text(line['text'])
        controls=line.get('controls',[])
        if type(controls) is not list or any(c not in ('page_break','line_break','pause') for c in controls):raise ValueError('unknown export control; select explicit prose first')
        content.append((speaker,text,escape(text).replace('\n','<br>'),'page_break' in controls))
    if format=='text':
        body=''.join(speaker+': '+text+'\n'+ ('\n' if page else '') for speaker,text,html,page in content)
        return title+'\n\n'+body+'\n'+default_credits()+'\n'
    body=''.join('<p><strong>'+escape(speaker)+':</strong> '+html+'</p>'+('<hr>' if page else '') for speaker,text,html,page in content)
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>'+escape(title)+'</title><style>body{max-width:52rem;margin:4rem auto;padding:0 1.5rem;font:18px/1.7 system-ui;color:#24313b}footer{margin-top:3rem}hr{border:0;border-top:1px solid #ccd5dc}</style><h1>'+escape(title)+'</h1>'+body+'<footer>'+default_credits()+'</footer></html>'


def export_walkthrough(coverage:dict,annotations:dict)->str:
    coverage=snapshot_json(coverage);annotations=snapshot_json(annotations)
    if type(annotations) is not dict or len(annotations)>512:raise ValueError('invalid walkthrough annotations')
    lines=['Walkthrough','']
    for goal in coverage.get('covered',[]):
        label(goal)
        if goal in annotations:lines.append(_text(annotations[goal]))
    unknown=coverage.get('unknown_edges',[])
    if unknown:
        for edge in unknown:label(edge)
        lines.extend(['','Unverified directions: '+', '.join(unknown)])
    lines.extend(['','Directions reflect recorded route assertions and author annotations.',default_credits(),''])
    return '\n'.join(lines)
