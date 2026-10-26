from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib, shutil, zipfile
from .patching import ROMANCER_VERSION, self_test, doctor
from .rom_ident import identify_rom
from .util import write_json

STABILITY={
'identify':'stable','init':'stable','snes-map':'stable','genesis-map':'stable','diff':'stable','make-ips':'stable','parse-trace':'stable','trace-summary':'stable','trace-filter':'stable','plan-breakpoints':'stable','debugger-guide':'stable','trace-window':'stable','correlate-trace':'stable','find-routine':'stable','resolve-pc':'stable','patch-plan':'stable','validate-patch':'stable','risk-score':'stable','asar-skeleton':'stable','ips-manifest':'stable','text-scan':'stable','pointer-scan':'stable','tile-dump':'stable','palette-dump':'stable','record-scan':'stable','backend-config':'experimental','launch':'experimental','watch-traces':'experimental','ai-prompt':'experimental','patch-build':'stable','patch-rebuild':'stable','package-release':'stable','export-debug-script':'experimental','trace-call-tree':'experimental',
'knowledge-export':'stable','knowledge-import-capsule':'stable','knowledge-diff-capsules':'stable','knowledge-audit-capsule':'stable','v16-self-test':'stable','prove':'stable','proof-compare':'stable','proof-bundle':'stable','v17-self-test':'stable','architecture-match':'stable','model-game':'stable','engine-template':'stable','v18-self-test':'stable','plan-feature':'stable','constraint-check':'stable','compile-feature':'experimental','v19-self-test':'stable','lab-lifecycle':'stable','final-certify':'stable','self-certify':'stable','publish-report':'stable','lab-plan':'stable','v20-self-test':'stable','cheat-schema':'stable','cheat-sources':'stable','cheat-audit-source':'stable','cheat-build-archive':'stable','v21-self-test':'stable','knowledge-vault':'stable','knowledge-inherit':'stable','profile-generate':'stable','game-sdk':'experimental','platform-scaffold':'stable','project-plan-v15':'experimental','self-evaluate-v15':'stable','technical-manual':'stable','v15-self-test':'stable','qa-next':'stable','qa-boundaries':'experimental','qa-run':'experimental','balance-report':'stable','pacing-report':'stable','save-torture-plan':'stable','cross-core-matrix':'stable','v14-self-test':'stable','repair-classify':'stable','semantic-patch':'experimental','semantic-merge':'experimental','repair-minimize':'experimental','assembly-recipe':'experimental','v13-self-test':'stable','architecture-callgraph':'experimental','architecture-schema':'experimental','event-opcodes':'experimental','architecture-reference':'stable','ghidra-export':'experimental','v12-self-test':'stable','live-debug-probe':'experimental','address-translate':'stable','mgba-bridge-template':'experimental','v11-self-test':'stable','debug-backends':'stable','debug-plan':'stable','causal-writers':'stable','causal-slice':'experimental','diagnose-cause':'experimental','patch-ledger':'stable','free-space':'experimental','patch-bisect':'experimental','testcase-minimize':'experimental','repair-search':'experimental','behavior-coverage':'stable','certify-v10':'stable','v10-self-test':'stable',
'play-session':'stable','play-belief':'stable','play-objective':'experimental','play-failure':'stable','play-plan':'stable','play-economy':'stable','genre-pack':'stable','runtime-autoplay':'experimental','v9-self-test':'stable',
'runtime-platform':'stable','runtime-doctor':'stable','runtime-run':'stable','runtime-scenario':'stable','runtime-controls':'experimental','runtime-explore':'experimental','runtime-suite':'stable','runtime-regression':'stable','runtime-goal-search':'experimental','runtime-state-capture':'stable','runtime-state-match':'stable','runtime-memory-find':'stable','runtime-memory-correlate':'stable','runtime-memory-rank':'stable','profile':'stable','scenario-template':'stable','v7-self-test':'stable'
}

STABILITY.update({
'vault-init':'stable','vault-status':'stable','artifact-add':'stable','artifact-audit':'stable','artifact-lineage':'stable','handoff-prompt':'stable','release-boundary-scan':'stable','version-diff':'stable',
'bridge-install-template':'stable','bridge-probe-v30':'experimental','bridge-read-memory':'stable','bridge-watch-v30':'experimental','bridge-break-v30':'experimental','bridge-snapshot-v30':'stable','bridge-run-scenario-v30':'experimental',
'visual-diff':'stable','sprite-grid-check':'stable','tile-usage-map':'stable','palette-consistency':'stable','text-render-check':'stable','menu-oracle':'stable','battle-text-oracle':'stable','portrait-check':'stable',
'sdk-create':'stable','sdk-audit':'stable','sdk-map-report':'stable','sdk-event-report':'stable','sdk-text-report':'stable','sdk-battle-report':'stable','sdk-save-report':'stable','sdk-export':'stable',
'alloc-space':'stable','hook-plan':'stable','asm-build':'experimental','patch-stack-v30':'stable','patch-collision-check-v30':'stable','rollback-build':'stable','patch-explain-v30':'stable',
'route-map':'stable','route-next':'stable','route-run':'stable','cutscene-lock-check':'stable','softlock-scan':'stable','optional-area-check':'stable','natural-route-validate':'stable',
'qa-matrix':'stable','menu-matrix':'stable','battle-matrix':'stable','economy-matrix':'stable','save-load-matrix':'stable','boss-matrix':'stable','random-battle-matrix':'stable','text-matrix':'stable','demo-certify':'stable',
'studio':'stable','studio-build':'stable','studio-report':'stable','dashboard-export':'stable','qa-board':'stable','visual-report':'stable',
'v30-new-project':'stable','v30-import-source':'stable','v30-build-sdk':'stable','certify-release':'stable','v30-status':'stable','v30-capabilities':'stable','v30-self-test':'stable',
})

def capabilities(out:str|None=None)->dict[str,Any]:
    result={'tool':'ROMancer','version':ROMANCER_VERSION,'policy':'Evidence-first. Candidate findings remain candidate until externally validated.','command_stability':STABILITY,
            'supported_systems':['nes','snes','genesis','gb','gbc','gba'],'patch_formats':['ips'],
            'runtime':{'frontend':'direct libretro ABI','software_video_capture':True,'joypad_input':True,'save_states':True,'exposed_memory':True,'save_ram_persistence':True,'disc_control':'when exposed by core','hardware_render_capture':False,'bounded_autonomous_play':True},
            'knowledge_commons':{'safe_capsules':True,'capsule_import_revalidation':True,'capsule_diff':True,'asset_leakage_audit':True},
            'formal_proof':{'invariant_gates':True,'comparison_modes':True,'proof_bundles':True,'declared_scope_only':True},
            'cross_engine_model':{'engine_ontology':True,'mechanic_ontology':True,'architecture_matching':True,'test_templates':True},
            'creator_studio':{'semantic_feature_planning':True,'constraint_checking':True,'feature_source_plan_compile':True,'unsafe_byte_build_blocked_without_evidence':True},
            'final_lab':{'lifecycle_gates':True,'final_certification':True,'self_certification':True,'release_report':True},
            'cheat_archive':{'source_inventory':True,'retroarch_cht_parser':True,'generic_csv_tsv_parser':True,'generic_json_jsonl_parser':True,'txt_tsv_jsonl_outputs':True,'source_audit':True,'runtime_cheat_validation':False},
            'v22_to_v30_lab':{'project_vault':True,'artifact_ledger':True,'handoff_generator':True,'release_boundary_scan':True,'bridge_templates':True,'visual_oracles':True,'game_sdk_scaffold':True,'patch_synthesis_helpers':True,'route_validation':True,'qa_matrices':True,'studio_dashboard':True,'release_certification':True},
            'cumulative_research':{'hash_scoped_vault':True,'inheritance_requires_revalidation':True,'automatic_profile_generation':True,'game_sdk_generation':True,'platform_scaffolding':True,'self_evaluation':True},
            'qa_laboratory':{'coverage_directed':True,'boundary_generation':True,'parallel_runner':True,'balance_analysis':True,'pacing_analysis':True,'save_system_plans':True,'cross_core_matrix':True},
            'repair_engineering':{'repair_classification':True,'semantic_field_patch':True,'semantic_merge':True,'repair_minimization':True,'assembly_recipe_validation':True},
            'self_improving':{'knowledge_inheritance':True,'automatic_profile_generation':True,'self_evaluation':True,'knowledge_vault':True,'platform_sdk_contract':True,'autonomous_project_planning':True},
            'architecture_reconstruction':{'dynamic_call_graph':True,'record_schema_inference':True,'event_opcode_learning':True,'ghidra_handoff':True},
            'live_debug':{'bridge_protocol':'newline-delimited JSON/TCP','address_translation':True,'mgba_socket_bridge_bootstrap':True,'configured_external_bridges_required':True},
            'autonomous_engineering':{'debug_adapter_contract':True,'offline_causal_slicing':True,'patch_hunk_bisection':True,'testcase_minimization':True,'patch_ownership_ledger':True,'bounded_parameter_repair':True,'behavior_coverage':True,'explicit_certification_gates':True,'unconfigured_live_debugger_control':False},
            'play_intelligence':{'belief_statuses':['VERIFIED','HIGH_CONFIDENCE','PLAUSIBLE','UNKNOWN','CONTRADICTED'],'session_memory':True,'failure_taxonomy':True,'resource_economics':True,'risk_aware_planner':True,'destructive_action_guard':True,'genre_hypothesis_packs':17,'universal_pixel_semantics':False},
            'live_debugger_control':'capability-negotiated; external mGBA/BlastEm/Mesen2 automation is not configured by default; synthetic mock/offline adapters are live within their documented scope',
            'bundled_emulator_cores':False,'bundled_bios_or_firmware':False,'bundled_commercial_game_content':False}
    if out: write_json(out,result)
    return result

def rom_doctor(rom:str,out:str|None=None)->dict[str,Any]:
    ident=identify_rom(rom)
    warnings=[]; safety='good'
    sysname=(ident.get('system') or '').lower()
    if 'unknown' in sysname: warnings.append('System detection uncertain. Do not patch until manually confirmed.'); safety='caution'
    if sysname.startswith('snes'):
        if ident.get('mapping') in (None,'unknown'): warnings.append('SNES mapping uncertain. Confirm LoROM/HiROM before address conversion.'); safety='caution'
        if ident.get('copier_header') is True: warnings.append('Copier header detected. Patch offsets must account for 0x200-byte header.'); safety='caution'
    if sysname.startswith('nes') and 'mapper' not in ident: warnings.append('NES mapper details not fully decoded. Banked addresses require mapper state.'); safety='caution'
    result={'tool':'ROMancer','feature':'ROM doctor','rom':rom,'identity':ident,'patch_safety':safety,'warnings':warnings}
    if out: write_json(out,result)
    return result

def clean_tree(root:str)->dict[str,Any]:
    rootp=Path(root); removed=[]
    for p in list(rootp.rglob('__pycache__')):
        shutil.rmtree(p, ignore_errors=True); removed.append(str(p))
    for p in rootp.rglob('*.pyc'):
        try: p.unlink(); removed.append(str(p))
        except OSError: pass
    return {'tool':'ROMancer','feature':'clean tree','root':str(rootp),'removed_count':len(removed),'removed':removed[:200]}

def full_self_test(out:str|None=None)->dict[str,Any]:
    base=self_test(); doc=doctor(); tests=list(base.get('tests',[])); ok=True
    for t in tests: ok = ok and bool(t.get('ok',False))
    from .v7 import v7_self_test
    from .v9 import v9_self_test
    from .v10 import v10_self_test
    from .v11 import v11_self_test
    from .v12 import v12_self_test
    from .v13 import v13_self_test
    from .v14 import v14_self_test
    from .v15 import v15_self_test
    from .v16 import v16_self_test
    from .v17 import v17_self_test
    from .v18 import v18_self_test
    from .v19 import v19_self_test
    from .v20 import v20_self_test
    from .v21 import v21_self_test
    from .v22_30 import v30_self_test
    from .v31 import v31_self_test
    runtime=v7_self_test()
    cognition=v9_self_test()
    engineering=v10_self_test()
    live_debug=v11_self_test()
    architecture=v12_self_test()
    repair=v13_self_test()
    qa=v14_self_test()
    self_improving=v15_self_test()
    commons=v16_self_test()
    proof=v17_self_test()
    cross_engine=v18_self_test()
    creator=v19_self_test()
    final_lab=v20_self_test()
    cheat_archive=v21_self_test()
    v30_lab=v30_self_test()
    v31_lab=v31_self_test()
    
    ok = ok and bool(runtime.get('ok',False)) and bool(cognition.get('ok',False)) and bool(engineering.get('ok',False)) and bool(live_debug.get('ok',False)) and bool(architecture.get('ok',False)) and bool(repair.get('ok',False)) and bool(qa.get('ok',False)) and bool(self_improving.get('ok',False)) and bool(commons.get('ok',False)) and bool(proof.get('ok',False)) and bool(cross_engine.get('ok',False)) and bool(creator.get('ok',False)) and bool(final_lab.get('ok',False)) and bool(cheat_archive.get('ok',False)) and bool(v30_lab.get('ok',False)) and bool(v31_lab.get('ok',False))
    result={'tool':'ROMancer','version':ROMANCER_VERSION,'feature':'full self-test','ok':ok,'base_self_test':base,'v7_self_test':runtime,'v9_self_test':cognition,'v10_self_test':engineering,'v11_self_test':live_debug,'v12_self_test':architecture,'v13_self_test':repair,'v14_self_test':qa,'v15_self_test':self_improving,'v16_self_test':commons,'v17_self_test':proof,'v18_self_test':cross_engine,'v19_self_test':creator,'v20_self_test':final_lab,'v21_self_test':cheat_archive,'v30_self_test':v30_lab,'v31_self_test':v31_lab,'doctor':doc,
            'notes':['Full self-test uses bundled deterministic fixtures, including a source-built mock libretro core when gcc/cc is available.',
                     'The Windows package includes pinned console engines; source installations need compatible cores. Real-game coverage requires user-supplied game content.']}
    if out: write_json(out,result)
    return result

def build_release(root:str,out_dir:str='dist',name:str|None=None)->dict[str,Any]:
    rootp=Path(root).resolve(); clean_tree(str(rootp)); dist=Path(out_dir); dist.mkdir(parents=True,exist_ok=True)
    name=name or f'ROMancer_v{ROMANCER_VERSION.replace(".","_")}'
    zip_path=dist/(name+'.zip')
    if zip_path.exists(): zip_path.unlink()
    excluded=[]
    forbidden_suffixes={'.srm','.sav','.state','.smc','.sfc','.nes','.gba','.gb','.gbc','.gen','.bin','.iso','.chd'}
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for p in rootp.rglob('*'):
            if not p.is_file(): continue
            rel=p.relative_to(rootp)
            if '.git' in p.parts or 'dist' in p.parts or '.romancer_runtime' in p.parts:
                excluded.append(str(rel)); continue
            if p.suffix.lower() in forbidden_suffixes:
                # Release ZIPs exclude binary ROM/disc/save-shaped payloads by suffix
                excluded.append(str(rel)); continue
            if p.name.endswith('.pyc') or '__pycache__' in p.parts:
                excluded.append(str(rel)); continue
            z.write(p, arcname=str(Path(rootp.name)/rel))
    sha=hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar=dist/(name+'.sha256')
    sidecar.write_text(f'{sha}  {zip_path.name}\n',encoding='utf-8')
    return {'tool':'ROMancer','feature':'release builder','root':str(rootp),'zip':str(zip_path),'sha256':sha,'excluded_runtime_or_sensitive_artifacts':excluded}
