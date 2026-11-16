"""Save and exchange exact-revision discoveries tied to measured edit checks."""

import json
from pathlib import Path

from .asset_schema import fields, label, number
from .assets import digest, inspect_assets
from .data_tables import inspect_table
from .release import publish_bytes
from .release_scope import require_supported
from .replay_proof import _sha256, checked_replay
from .script_schema import canonical_bytes
from . import workbench_projects as projects


DISCOVERY_LIMIT = 256 * 1024


def _one_byte(name, offset):
    return {'schema_version':1, 'name':name, 'offset':offset, 'count':1, 'stride':1,
            'fields':[{'name':name, 'offset':0, 'type':'u8', 'endian':'little', 'pointer_base':None}]}


def _read_layout(path, row, kind, definition, resource):
    if kind in ('byte', 'table'):
        if resource is not None:
            raise ValueError('This discovery opens a numeric table.')
        inspection = inspect_table(path, row['sha256'], definition, 0, 1 if kind == 'byte' else 50)
        layout = inspection['definition']
        if kind == 'byte' and layout != _one_byte(layout['name'], layout['offset']):
            raise ValueError('A named byte must use a single unsigned byte.')
        return layout, inspection, (layout['offset'], layout['count'] * layout['stride'])
    if kind == 'graphics':
        label(resource, 80)
        inspection = inspect_assets(path, definition)
        if not inspection.get('ok') or not inspection.get('write_supported'):
            raise ValueError('This graphics layout is unavailable for editing.')
        spans = [item for group in ('bitmaps', 'palettes', 'tilemaps') for item in definition[group]
                 if item['id'] == resource]
        if len(spans) != 1:
            raise ValueError('Choose one uniquely identified tile, palette or tilemap resource.')
        return definition, inspection, (spans[0]['offset'], spans[0]['length'])
    raise ValueError('Choose a named byte, numeric table or graphics resource.')


def _document(value, row, path):
    value = json.loads(canonical_bytes(value, max_bytes=DISCOVERY_LIMIT))
    fields(value, 'format name kind source_sha256 definition resource target_sha256 original_frame build_frame')
    if value['format'] != 'romancer-discovery-v1' or value['source_sha256'] != row['sha256']:
        raise ValueError('This discovery belongs to different ROM bytes. Choose the exact original revision.')
    label(value['name'], 80)
    for key in ('target_sha256', 'original_frame', 'build_frame'):
        _sha256(value[key])
    if value['target_sha256'] == row['sha256']:
        raise ValueError('This discovery needs a different edited build.')
    definition, inspection, span = _read_layout(path, row, value['kind'], value['definition'], value['resource'])
    value['definition'] = definition
    return value, inspection, span


def _changed(source, target, span, cancelled):
    offset, remaining = span
    with Path(source['path']).open('rb') as original, Path(target['path']).open('rb') as edited:
        original.seek(offset)
        edited.seek(offset)
        while remaining:
            if cancelled():
                raise KeyboardInterrupt
            amount = min(65536, remaining)
            left, right = original.read(amount), edited.read(amount)
            if len(left) != amount or len(right) != amount:
                raise ValueError('The discovery range extends past this build.')
            if left != right:
                return True
            remaining -= amount
    return False


def discovery_summaries(project, row):
    stored = row.get('discoveries', {})
    return [{'id':ident, 'name':r['document']['name'], 'kind':r['document']['kind'],
             'status':_status(project, row, r)}
            for ident, r in stored.items()]


def _status(project, row, record):
    evidence_id = record.get('evidence_id')
    if evidence_id is None:
        return 'IMPORTED'
    try:
        document = record['document']
        report = checked_replay(project, evidence_id, numeric=document['kind'] != 'graphics')
        if (row['sha256'] == report['source_sha256'] and document['target_sha256'] == report['target_sha256']
                and [document['original_frame'], document['build_frame']] ==
                    [report['runs'][0]['frame']['sha256'], report['runs'][2]['frame']['sha256']]):
            return 'REPLAY_CHECKED'
    except (ValueError, OSError):
        pass
    return 'CHECK_AGAIN'


class DiscoveryTools:
    def __init__(self, api):
        self.api = api

    def routes(self):
        return {
            'discoveries.save':('project_id artifact_id evidence_id name kind offset resource', self.save),
            'discoveries.open':('project_id artifact_id discovery_id', self.open),
            'discoveries.export':('project_id artifact_id discovery_id', self.export),
            'discoveries.import':('project_id artifact_id document', self.import_document),
            'discoveries.remove':('project_id artifact_id discovery_id', self.remove),
        }

    def save(self, p, cancelled):
        project, source, path = self.api.source(p)
        require_supported(source)
        if source['kind'] != 'source':
            raise ValueError('Save discoveries on the original ROM.')
        name, kind = label(p['name'], 80), p['kind']
        report = checked_replay(project, p['evidence_id'], numeric=kind != 'graphics')
        if (report['source_id'] != source['artifact_id'] or report['source_sha256'] != source['sha256']
                or kind == 'graphics' and not report.get('changed_pixels')):
            raise ValueError('Choose a passing check on this original with evidence for the edit.')
        target = projects.artifact(project, report['target_id'])
        if target['sha256'] != report['target_sha256'] or target['size'] != source['size']:
            raise ValueError('Save this discovery from a same-size build with the checked identity.')
        resource = p['resource']
        if kind == 'byte':
            definition = _one_byte(name, number(p['offset'], 0, source['size'] - 1))
        elif kind == 'table':
            definition = source.get('descriptors', {}).get('tables', {}).get('definition')
            if not definition:
                raise ValueError('Save the table layout on this original first.')
        elif kind == 'graphics':
            definition = source.get('descriptors', {}).get('assets')
            if not definition:
                raise ValueError('Save the graphics layout on this original first.')
        else:
            raise ValueError('Choose a supported discovery type.')
        document, _, span = _document({
            'format':'romancer-discovery-v1', 'name':name, 'kind':kind, 'source_sha256':source['sha256'],
            'definition':definition, 'resource':resource, 'target_sha256':target['sha256'],
            'original_frame':report['runs'][0]['frame']['sha256'], 'build_frame':report['runs'][2]['frame']['sha256'],
        }, source, path)
        projects._measure(target['path'], target, cancelled=cancelled)
        if not _changed(source, target, span, cancelled):
            raise ValueError('Nothing in this resource changed in the checked build.')
        projects._measure(target['path'], target, cancelled=cancelled)
        return self._store(project, source, document, p['evidence_id'], cancelled)

    def import_document(self, p, cancelled):
        project, source, path = self.api.source(p)
        require_supported(source)
        if source['kind'] != 'source':
            raise ValueError('Import a discovery on its exact original ROM.')
        document, _, _ = _document(p['document'], source, path)
        return self._store(project, source, document, None, cancelled)

    def _store(self, project, source, document, evidence_id, cancelled):
        ident = digest(document)
        with projects.locked(project) as value:
            projects._measure(source['path'], source, cancelled=cancelled)
            row = next(r for r in value['sources'] if r['artifact_id'] == source['artifact_id'])
            stored = row.setdefault('discoveries', {})
            if ident not in stored and len(stored) >= 32:
                raise ValueError('Remove an unused discovery before saving another. Each ROM holds 32.')
            if evidence_id is not None or ident not in stored:
                stored[ident] = {'document':document, 'evidence_id':evidence_id}
                canonical_bytes(stored, max_bytes=512 * 1024)
                projects.write_json(project/'project.json', value)
            status = _status(project, source, stored[ident])
        return {'ok':True, 'status':status, 'discovery_id':ident}

    def open(self, p, cancelled):
        project, source, path = self.api.source(p)
        ident = projects.identifier(p['discovery_id'])
        record = source.get('discoveries', {}).get(ident)
        if record is None or digest(record['document']) != ident:
            raise ValueError('This discovery is unavailable on the selected original.')
        document, inspection, _ = _document(record['document'], source, path)
        return {'ok':True, 'status':_status(project, source, record), 'source_sha256':source['sha256'],
                'document':document, 'inspection':inspection}

    def export(self, p, cancelled):
        opened = self.open(p, cancelled)
        project = self.api.project(p)
        path = self.api._export_path(project, 'json')
        document = opened['document']
        publish_bytes(path, canonical_bytes(document, max_bytes=DISCOVERY_LIMIT), cancelled=cancelled)
        return {'ok':True, 'status':'EXPORTED',
                'export':self.api._record_export(project, path, 'documentation', title=document['name'] + '-discovery')}

    def remove(self, p, cancelled):
        project, source, path = self.api.source(p)
        ident = projects.identifier(p['discovery_id'])
        with projects.locked(project) as value:
            if cancelled():
                raise KeyboardInterrupt
            row = next((r for r in value['sources'] if r['artifact_id'] == source['artifact_id']), None)
            if not row or ident not in row.get('discoveries', {}):
                raise ValueError('This discovery is unavailable on the selected original.')
            del row['discoveries'][ident]
            projects.write_json(project/'project.json', value)
        return {'ok':True, 'status':'REMOVED'}
