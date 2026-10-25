"""Stable-ID text exchange; only the translation column may change."""
import csv
import io
from pathlib import Path
from . import workbench_projects as p
from .script import inspect_script,compile_changes,ScriptError
from .script_schema import canonical_bytes
from .workbench_files import input_file,read_bounded

COLUMNS=('record_id','segment','document_id','source_sha256','schema_sha256','original','translation','capacity','controls')
FORMULA_PREFIXES=('=','+','-','@','\t','\r',"'")


def escape_cell(text):return "'"+text if text.startswith(FORMULA_PREFIXES) else text
def unescape_cell(text):return text[1:] if text.startswith("'") and text[1:].startswith(FORMULA_PREFIXES) else text


def _separator(fmt):
    if fmt not in ('csv','tsv'):raise ValueError('Choose CSV or TSV.')
    return ',' if fmt=='csv' else '\t'


def _document(project,artifact_id,schema):
    row=p.artifact(project,artifact_id);p._measure(row['path'],row);document=inspect_script(Path(row['path']),schema)
    if not document['ok'] or not document['write_supported']:raise ValueError('Inspect an editable, revision-bound text declaration first.')
    rows=[]
    for record in document['records']:
        controls=' '.join(t['raw_hex'] for t in record['tokens'] if t['kind']=='control')
        for segment in record['segments']:
            rows.append({'record_id':record['id'],'segment':str(segment['index']),**{k:document[k] for k in ('document_id','source_sha256','schema_sha256')},
                'original':segment['text'],'translation':segment['text'],'capacity':str(record['capacity']),'controls':controls})
    if not rows or len(rows)>2000:raise ValueError('Translation sheets support 1..2000 declared text segments.')
    return row,document,rows


def export_sheet(project,artifact_id,schema,fmt):
    separator=_separator(fmt);_,_,rows=_document(project,artifact_id,schema);output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=COLUMNS,delimiter=separator,lineterminator='\r\n');writer.writeheader()
    writer.writerows({k:escape_cell(value) for k,value in row.items()} for row in rows)
    text=output.getvalue()
    if len(text.encode('utf-8-sig'))>4*1024**2:raise ValueError('Sheet exceeds 4 MiB. Export a smaller declared resource.')
    return text


def preview_sheet(project,artifact_id,schema,input_id,fmt,*,cancelled=lambda:False):
    separator=_separator(fmt);row,document,expected=_document(project,artifact_id,schema);entry,path=input_file(project,input_id,'translation')
    try:
        text=read_bounded(path,4*1024**2,entry,cancelled=cancelled).decode('utf-8-sig');reader=csv.DictReader(io.StringIO(text,newline=''),delimiter=separator,strict=True)
        if tuple(reader.fieldnames or ())!=COLUMNS:raise ValueError('Keep all exported column names and their order; edit only translation.')
        imported=[]
        for incoming in reader:
            if cancelled():raise KeyboardInterrupt
            if len(imported)>=2000 or None in incoming or any(v is None for v in incoming.values()):raise ValueError('Sheet has too many rows, missing fields or extra columns.')
            imported.append({k:unescape_cell(v) for k,v in incoming.items()})
    except (UnicodeError,csv.Error):raise ValueError('Save a valid UTF-8 CSV/TSV sheet with the original headers.') from None
    by_id={(r['record_id'],r['segment']):r for r in expected};seen=set();changes=[]
    for incoming in imported:
        key=(incoming['record_id'],incoming['segment']);original=by_id.get(key)
        if original is None or key in seen:raise ValueError('Unknown or duplicated record ID / segment. Start with a fresh export.')
        seen.add(key)
        if any(incoming[k]!=original[k] for k in COLUMNS if k!='translation'):raise ValueError('Source, schema, original text, controls or capacity changed. Edit only translation in a fresh export.')
        if len(incoming['translation'])>65536:raise ValueError('A translation segment exceeds 65,536 characters.')
        if incoming['translation']!=original['original']:changes.append({'record_id':key[0],'segment':int(key[1]),'text':incoming['translation']})
    if seen!=set(by_id):raise ValueError('Sheet is missing exported text rows. Keep every row and stable ID.')
    edits={'schema_version':1,**{k:document[k] for k in ('document_id','source_sha256','schema_sha256')},'changes':changes}
    issues=[];previews=[];groups={}
    for change in changes:groups.setdefault(change['record_id'],[]).append(change)
    records={r['id']:r for r in document['records']}
    for record_id,group in groups.items():
        record=records[record_id];updated={c['segment']:c['text'] for c in group};tokens=record['tokens']
        used=sum(len(updated.get(s['index'],s['text'])) for s in record['segments'])+sum(t['length'] for t in tokens if t['kind'] in ('control','terminator'))
        previews.append({'record_id':record_id,'offset':record['offset'],'used_bytes':used,'capacity':record['capacity'],
                         'before':[s['text'][:512] for s in record['segments']],
                         'after':[updated.get(s['index'],s['text'])[:512] for s in record['segments']],
                         'text_truncated':any(len(updated.get(s['index'],s['text']))>512 for s in record['segments'])})
        if used>record['capacity']:issues.append({'record_id':record_id,'offset':record['offset'],'code':'CAPACITY','message':'Translated text exceeds this fixed byte allocation. Shorten the text.','used_bytes':used,'capacity':record['capacity']})
        encoding={g['text'] for g in schema['format']['encoding']['glyphs']}
        for change in group:
            if any(scalar not in encoding for scalar in change['text']):issues.append({'record_id':record_id,'segment':change['segment'],'offset':record['offset'],'code':'UNENCODABLE_TEXT','message':'Text contains a character outside the declared encoding. Controls cannot be inserted as text.','used_bytes':used,'capacity':record['capacity']})
    if len(changes)>1024:issues.append({'record_id':None,'offset':None,'code':'EDIT_BUDGET','message':'Change at most 1024 segments per build. Keep remaining translations for a later build.'})
    if not issues:
        try:compile_changes(document,schema,edits)
        except (ValueError,RecursionError) as error:issues.append({'record_id':None,'offset':None,'code':getattr(error,'code','EDIT_BUDGET'),'message':str(error)})
    p._measure(row['path'],row,cancelled=cancelled)
    return {'ok':True,'status':'READY_TO_REVIEW' if not issues and changes else 'CHECK_TRANSLATIONS' if issues else 'NO_CHANGES',
            'valid':not issues,'project_id':Path(project).name,'artifact_id':artifact_id,'source_sha256':row['sha256'],
            'input_id':input_id,'schema_sha256':document['schema_sha256'],'document_id':document['document_id'],
            'changed_segments':len(changes),'previews':previews,'issues':issues,'edits':edits if not issues else None,
            'controls_preserved':True,'original_preserved':True}
