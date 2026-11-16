"""Portable cold-start replay checks for verified BPS exports."""

import base64
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

from .asset_schema import fields, label
from .build_checks import validate_config, validate_expectations
from .release import publish_bytes
from .release_scope import SYSTEMS
from .script_schema import canonical_bytes
from .streaming_bps import create_patch
from .workbench_evidence import load_evidence
from . import workbench_projects as projects


PROOF_LIMIT = 32 * 1024


def _sha256(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected a SHA-256 identity.')
    return value


def _config(proof):
    return validate_config({'name':'Shared replay check', 'automatic':False, 'mode':'review_changes',
                            'steps':proof['steps'], 'region':proof['region'], 'route_ids':[]})


def validate_proof(proof):
    proof = json.loads(canonical_bytes(proof, max_bytes=PROOF_LIMIT))
    fields(proof, 'format system source_sha256 target_sha256 patch_sha256 context execution_sha256 steps region original_frame build_frame expectations observed_values')
    if proof['format'] != 'romancer-replay-proof-v1' or proof['system'] not in SYSTEMS:
        raise ValueError('Unsupported ROMancer replay proof.')
    for name in ('source_sha256', 'target_sha256', 'patch_sha256', 'execution_sha256', 'original_frame', 'build_frame'):
        _sha256(proof[name])
    if proof['source_sha256'] == proof['target_sha256']:
        raise ValueError('Replay proof needs a separate edited build.')
    context = proof['context']
    fields(context, 'core_sha256 core_options controller_devices system_files')
    _sha256(context['core_sha256'])
    if (type(context['core_options']) is not dict or type(context['controller_devices']) is not dict
            or context['system_files'] != []):
        raise ValueError('This proof format requires cartridge-only execution with the listed engine settings.')
    _config(proof)
    expectations = validate_expectations(proof['expectations'])
    values = proof['observed_values']
    if (type(values) is not list or len(values) != 2 or any(type(row) is not list or len(row) != len(expectations)
            or any(type(value) is not int or abs(value) > 2**32 - 1 for value in row) for row in values)):
        raise ValueError('The proof needs two bounded sets of observed gameplay values.')
    return proof


def checked_replay(project, evidence_id, *, numeric=False):
    record = load_evidence(project, evidence_id, 'regression')
    report = record['report']
    if (not record['runtime_trusted'] or report.get('scope') != 'automatic_build_check_v1'
            or report.get('replay_verified') is not True
            or (numeric and report.get('gameplay_verified') is not True)):
        raise ValueError('Run a passing cold-start replay check for this edit first.')
    return report


class ReplayProofTools:
    def __init__(self, api):
        self.api = api

    def routes(self):
        return {
            'release.proof': ('project_id source_id target_id evidence_id title description screenshots', self.export),
            'release.replay': ('project_id source_id target_id input_id proof', self.replay),
        }

    def export(self, p, cancelled):
        project = self.api.project(p)
        report = checked_replay(project, p['evidence_id'])
        source = projects.artifact(project, p['source_id'])
        target = projects.artifact(project, p['target_id'])
        if source['kind'] != 'source' or target['kind'] != 'build':
            raise ValueError('Replay exports require a check from the original ROM to an edited build.')
        if any(report[role + '_id'] != row['artifact_id'] or report[role + '_sha256'] != row['sha256']
               for role, row in (('source', source), ('target', target))):
            raise ValueError('Choose the original and build used in this replay check.')
        title = label(p['title'], 120)
        description = label(p['description'], 500, blank=True)
        if type(p['screenshots']) is not bool:
            raise ValueError('Choose whether to include the screenshots.')
        config, runs = report['configuration'], report['runs']
        proof = validate_proof({
            'format':'romancer-replay-proof-v1', 'system':report['system_id'],
            'source_sha256':source['sha256'], 'target_sha256':target['sha256'],
            'patch_sha256':'0' * 64, 'context':report['replay_context'],
            'execution_sha256':runs[0]['execution_sha256'], 'steps':config['steps'], 'region':config['region'],
            'original_frame':runs[0]['frame']['sha256'], 'build_frame':runs[2]['frame']['sha256'],
            'expectations':[r['rule'] for r in report.get('gameplay', {}).get('results', [])],
            'observed_values':[runs[0].get('values', []), runs[2].get('values', [])],
        })
        projects._measure(source['path'], source, cancelled=cancelled)
        projects._measure(target['path'], target, cancelled=cancelled)
        if max(source['size'], target['size']) > 64 * 1024**2:
            raise ValueError('Replay proof packages support cartridges up to 64 MiB.')
        patch_path = self.api._export_path(project, 'bps')
        path = self.api._export_path(project, 'zip')
        try:
            patch = create_patch(Path(source['path']), Path(target['path']), patch_path,
                                 {'title':title, 'description':description}, cancelled=cancelled)
            if patch.get('source_sha256') != source['sha256'] or patch.get('target_sha256') != target['sha256']:
                raise ValueError('The verified patch differs from the replayed cartridge identities.')
            proof['patch_sha256'] = projects._measure(patch_path, cancelled=cancelled)['sha256']
            details = ['Original SHA-256: ' + source['sha256'], 'Build SHA-256: ' + target['sha256'],
                       'Patch SHA-256: ' + proof['patch_sha256'], 'Engine SHA-256: ' + proof['context']['core_sha256']]
            for row in report.get('gameplay', {}).get('results', []):
                details.append(f"{row['rule']['name']} ({row['rule']['mode']}): original {row['original']}, build {row['build']}.")
            instructions = ("ROMancer replay proof\n\n" + title + "\n" + description + "\n\n" +
                "\n".join(details) + "\n\nOpen your exact original ROM, then open Export. In Apply a downloaded patch, "
                "preview Patch.bps and create the patched build. Back in Export, pick the original and patched build, "
                "then select Patch.bps and Replay.json in Verify a shared replay. Run the replay to check the frames "
                "and any listed gameplay values with the matching engine.\n\nBy RetchEWretched\n")
            archive_bytes = BytesIO()
            with ZipFile(archive_bytes, 'w', ZIP_DEFLATED) as archive:
                archive.write(patch_path, 'Patch.bps')
                archive.writestr('README.txt', instructions)
                archive.writestr('Replay.json', canonical_bytes(proof, max_bytes=PROOF_LIMIT))
                if p['screenshots']:
                    for key, name in (('original','Original'), ('build','Build'), ('difference','Difference')):
                        image = base64.b64decode(report['visual'][key + '_png_base64'], validate=True)
                        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
                            raise ValueError('Stored screenshot is not a PNG.')
                        archive.writestr(name + '.png', image)
            publish_bytes(path, archive_bytes.getvalue(), cancelled=cancelled)
        finally:
            patch_path.unlink(missing_ok=True)
        return {'ok':True, 'status':'EXPORTED', 'proof':proof,
                'export':self.api._record_export(project, path, 'package', proof, title=title + '-replay-proof')}

    def replay(self, p, cancelled):
        from .release import verify_patch
        from .workbench_files import input_file

        project = self.api.project(p)
        proof = validate_proof(p['proof'])
        source = projects.artifact(project, p['source_id'])
        target = projects.artifact(project, p['target_id'])
        if (source['kind'] != 'source' or target['kind'] != 'build'
                or source['sha256'] != proof['source_sha256'] or target['sha256'] != proof['target_sha256']
                or source['system_id'] != proof['system'] or target['system_id'] != proof['system']):
            raise ValueError('This proof requires the exact original ROM and matching patched build.')
        patch, patch_path = input_file(project, p['input_id'], 'patch')
        if patch['sha256'] != proof['patch_sha256']:
            raise ValueError('The selected BPS patch does not match the shared proof.')
        verified = verify_patch(Path(source['path']), patch_path, target['sha256'], cancelled=cancelled)
        if verified.get('status') != 'VERIFIED' or not verified.get('ok'):
            raise ValueError('The BPS patch did not independently reconstruct the selected build.')
        if projects._measure(patch_path, patch, cancelled=cancelled)['sha256'] != proof['patch_sha256']:
            raise ValueError('The selected BPS patch changed during verification.')
        return self.api.checks._run(p, cancelled, _config(proof), expectations=proof['expectations'], proof=proof)
