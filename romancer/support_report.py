"""Allowlisted diagnostics. Never export arbitrary paths, text, errors or payloads."""
import importlib.util
from pathlib import Path
import platform
import shutil
from . import ROMANCER_VERSION,ROMANCER_RELEASE_NAME,workbench_projects as p
from .assets import checked_path



def collect_report(workspace,project=None,*,cancelled=lambda:False):
    workspace=checked_path(Path(workspace));checks=[]
    def check(code,status):checks.append({'code':code,'status':status})
    try:check('WORKSPACE_SPACE','PASS' if shutil.disk_usage(workspace).free>=256*1024**2 else 'LOW')
    except OSError:check('WORKSPACE_SPACE','UNAVAILABLE')
    pillow=importlib.util.find_spec('PIL') is not None;check('IMAGE_LIBRARY','PASS' if pillow else 'MISSING')
    setups={}
    from .runtime_profiles import load_profile,validate_profile
    for system in ('nes','snes','genesis','gb','gbc','gba','sms'):
        if cancelled():raise KeyboardInterrupt
        try:
            profile=load_profile(workspace,system)['profile']
            if profile is None:setups[system]='NOT_CONFIGURED'
            else:validate_profile(profile);setups[system]='INPUTS_VERIFIED'
        except (ValueError,OSError,KeyError,TypeError):setups[system]='NEEDS_ATTENTION'
    summary=None
    if project is not None:
        from .project_checks import validate_project,CHECK_CODES
        try:
            value=p.read_project(project);validation=validate_project(project,cancelled=cancelled)
            codes=sorted({r['code'] for r in validation['issues'] if r['code'] in CHECK_CODES})
            tests={status:0 for status in ('PASS','FAIL','REGRESSION','BLOCKED','HISTORICAL','OTHER')}
            reports=sorted((Path(project)/'reports').glob('*.json'))
            for path in reports[:512]:
                try:
                    from .workbench_evidence import load_evidence
                    record=load_evidence(project,path.stem);status=record['report'].get('status') if record['runtime_trusted'] else 'HISTORICAL'
                    tests[status if status in tests else 'OTHER']+=1
                except (ValueError,OSError,KeyError,TypeError):tests['OTHER']+=1
            summary={'sources':len(value['sources']),'builds':len(value['builds']),'validation':validation['status'],
                     'errors':validation['errors'],'warnings':validation['warnings'],'issue_codes':codes,
                     'test_report_counts':tests,'test_reports_truncated':len(reports)>512}
            check('PROJECT_CHECKS','NEEDS_ATTENTION' if validation['errors'] else 'PASS')
        except (ValueError,OSError,KeyError,TypeError):check('PROJECT_CHECKS','UNAVAILABLE')
    return {'ok':True,'format':'romancer-support-v1','release':ROMANCER_RELEASE_NAME,'internal_version':ROMANCER_VERSION,
            'python':platform.python_version(),'operating_system':platform.system(),'machine':platform.machine(),
            'checks':checks,'system_setups':setups,'project':summary,
            'privacy':'Only allowlisted versions, check codes, statuses and counts. No ROM data, paths, names, credentials or raw errors.'}
