"""Package approved source directories, never the whole working project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from romancer.cd_patch import check_output_paths

DIRECTORIES = {'romancer', 'examples', 'profiles', 'tests', 'tools', 'knowledge', '.github', 'user-guide'}
ROOT_FILES = {'README.txt', 'run.sh', 'run.ps1', 'Launch ROMancer.cmd',
              'launch.ps1', 'desktop_window.ps1', 'requirements.txt', 'THIRD_PARTY_NOTICES.txt',
              'LICENSE', 'NSIS-LICENSE.txt', '.gitignore', '.gitattributes', '.editorconfig',
              'package.json', 'package-lock.json'}
EXCLUDED = {'__pycache__', '.git', '.venv', '.superpowers', 'work_private', 'private',
            'reports', 'evidence', 'saves', 'states', 'bios', 'roms', 'dist',
            '.romancer-history', '.romancer-evidence'}
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
# Release source selection is explicit. Adding a file or fixture requires review;
# a text extension or placement under docs/tests never grants distribution approval.
APPROVED_FILES = frozenset(ROOT_FILES | {
    f'{directory}/{name}'
    for directory, names in {
        '.github': 'workflows/ci.yml ISSUE_TEMPLATE/bug_report.yml',
        'romancer': '''
            research_tools.py popular_references.py documented_tables.py documented_names.py source_symbols.py ui/research_tools.js ui/popular_references.js ui/documented_tables.js ui/source_symbols.js
            mcp_server.py bundled_cores.py core_pins.py controller_devices.py ui/workspace_status.js ui/workspace_resume.js ui/shortcuts.js ui/tool_help.js
            ui/tool_inputs.js ui/patch_controls.js ui/revision_controls.js ui/hex_editor.js ui/build_history.js ui/project_checks.js ui/save_manager.js ui/translation_controls.js ui/visual_controls.js ui/workbench_usability.js
            ui/desktop_entry.js ui/app.bundle.js ui/bundle.json
            rom_health.py ui/rom_health.js
            ui/startup.js ui/preferences.js workflow_recipes.py memory_watches.py ui/memory_watches.js ui/views/automation.js runtime_library.py ui/audio_live.js ui/playback_controls.js help_content.py ui/project_flow.js ui/views/help.js resource_discovery.py ui/discovery_controls.js data_tables.py ui/views/tables.js resource_compression.py ui/compression_controls.js resource_exports.py ui/pixel_tools.js ui/pixel_history.js ui/tilemap_editor.js
            workbench_files.py workbench_tools.py patch_import.py binary_tools.py revision_catalog.py hex_tools.py build_history.py project_checks.py support_report.py save_manager.py translation_sheets.py visual_checks.py verified_games.py ui/verified_games.js
            graphics_discovery.py ui/graphics_investigation.js rom_scan.py project_lifecycle.py ui/rom_scan.js ui/project_manager.js ui/sprite_assembly.js
            level_design.py studio_tools.py studio_examples.py ui/level_canvas.js ui/views/levels.js
            value_search.py studio_discovery.py source_information.py release_scope.py ui/value_finder.js ui/animation_studio.js ui/source_support.js ui/edit_preview.js ui/game_visuals.js ui/palette_editor.js
            audio_systems.py sound_codecs.py sound_studio.py ui/sound_preview.js ui/views/sound.js
            __init__.py __main__.py address_translate_v11.py advanced_recon.py
            advanced_trace.py architecture_v12.py audit.py autonomous_play.py
            backend.py backend_scripts.py bisect_v10.py causal_v10.py cd_patch.py
            cdrom.py certify_v10.py cheat_archive_v21.py cli.py coverage_v10.py
            contracts.py contracts_cli.py history.py history_cli.py
            audio_capture.py runtime_client.py runtime_protocol.py runtime_worker.py
            capture_cli.py capture_ingest.py capture_runtime.py capture_store.py
            script.py script_cli.py script_patch.py script_schema.py
            dialogue_layout.py font_metrics.py layout_cli.py menu.py menu_cli.py
            menu_compare.py menu_metrics.py menu_schema.py
            asset_codecs.py asset_schema.py assets.py asset_patch.py
            audio_export.py audio_export_runtime.py runtime_session.py
            debug.py debug_schema.py debug_trace.py debug_runtime.py engineering_cli.py
            workbench_projects.py workbench_evidence.py replay_schema.py replay.py
            battle_analysis.py coverage.py regression.py player_docs.py release.py
            workbench_api.py workbench_jobs.py workbench_runtime.py workbench_server.py
            workbench_demo.py ui/index.html ui/mark.svg ui/theme.css ui/styles.css
            resource_catalog.py streaming_bps.py patch_sets.py system_registry.py system_reader.py project_portability.py draft_store.py container_workspace.py system_integrity.py resource_forms.py runtime_profiles.py system_addresses.py route_editor.py ui/interface_scale.js ui/declarations.js ui/asset_controls.js ui/runtime_setup.js ui/route_controls.js
            system_identify.py system_formats/__init__.py system_formats/nes.py
            system_resources.py system_demo.py boot_fixtures.py
            systems_cli.py
            system_formats/gb.py system_formats/snes.py system_formats/genesis.py system_formats/sms.py system_formats/gba.py system_formats/segacd.py
            ui/app.js ui/api.js ui/common.js ui/icons.js ui/views/overview.js
            ui/views/resources.js ui/views/scripts.js ui/views/assets.js
            ui/views/playtest.js ui/views/debug.js ui/views/routes.js
            ui/views/regression.js ui/views/release.js ui/views/settings.js
            creator_studio_v19.py cross_engine_v18.py debug_adapter_v10.py
            debug_export.py diffing.py evidence.py final_lab_v20.py frame_analysis.py
            game_profiles.py gameplay_beliefs.py gameplay_failures.py
            gameplay_genres.py gameplay_objectives.py gameplay_planner.py
            gameplay_resources.py gameplay_state.py hardening.py ips.py knowledge.py
            knowledge_commons_v16.py knowledge_v15.py libretro_frontend.py
            live_debug_v11.py memory_learning.py minimize_v10.py patch_ledger_v10.py
            patching.py playtest.py project.py proof_v17.py qa_lab_v14.py recon.py
            repair_engine_v13.py repair_v10.py rom_ident.py runtime_agent.py
            runtime_goal.py runtime_regression.py state_model.py trace_parser.py
            util.py v3.py v4.py v5.py v6.py v7.py v9.py v10.py v11.py v12.py v13.py
            v14.py v15.py v16.py v17.py v18.py v19.py v20.py v21.py v22_30.py v31.py
            workflow.py workspace.py systems/gba.py systems/genesis.py systems/nes.py
            systems/segacd.py systems/snes.py
        ''',
        'examples': '''
            ascii.tbl blastem_trace_sample.log bsnes_plus_trace_sample.log
            fake_trace.log mesen_trace_sample.log runtime/ff6_field_menu_template.json
            runtime/runtime_scenario_template.json
            runtime/shadowrun_pause_template.json runtime/suite_manifest_template.json
            v9/failure_execution.json v9/farm_plan.json v9/planner_uncertain.json
            v9/structured_objective.json v10/certification_manifest.template.json
            v10/coverage_manifest.json v10/reproducer.template.json
            v15/profile_evidence.template.json v15/self_evaluation.template.json
            v21/sample_generic_export.csv v21/sample_retroarch_fixture.cht
        ''',
        'profiles': '''
            final_fantasy_iii_snes.json generic_jrpg.json shadowrun_genesis.json
        ''',
        'knowledge/genre_packs': '''
            action.json action_rpg.json adventure.json fighting.json jrpg.json
            metroidvania.json platformer.json puzzle.json racing.json roguelike.json
            shooter.json srpg.json stealth.json strategy.json survival_horror.json
            universal.json visual_novel.json
        ''',
        'tests': '''
            test_research_tools.py test_popular_references.py test_documented_tables.py test_source_symbols.py ui_research_tools.mjs ui_popular_references.mjs ui_documented_tables.mjs ui_source_symbols.mjs
            test_download_input.py test_sms_format.py ui_sms_input.mjs
            test_mcp_server.py test_bundled_cores.py test_controller_devices.py test_setup_installer.py ui_controller_choices.mjs ui_workspace_status.mjs ui_shortcuts.mjs ui_tool_help.mjs ui_workspace_resume.mjs
            test_level_design.py test_studio_tools.py test_value_search.py test_studio_discovery.py test_source_information.py test_release_scope.py ui_level_design.mjs ui_animation_studio.mjs ui_value_finder.mjs ui_edit_previews.mjs ui_game_visuals.mjs ui_visual_live.mjs ui_publish_drafts.mjs ui_audio_preview.mjs
            test_sound_studio.py test_audio_systems.py ui_sound_studio.mjs
            test_graphics_discovery.py ui_graphics_investigation.mjs test_rom_scan.py test_project_lifecycle.py ui_rom_scan.mjs ui_project_manager.mjs ui_sprite_assembly.mjs
            test_verified_games.py test_save_seed.py ui_verified_games.mjs test_revision_catalog.py test_hex_history.py test_project_support.py test_save_manager.py test_translation_sheets.py test_visual_checks.py test_windows_publication.py ui_visual_checks.mjs ui_workbench_usability.mjs ui_translation.mjs ui_save_manager.mjs ui_project_checks.mjs ui_hex_editor.mjs ui_resources_races.mjs ui_source_encoding.mjs ui_build_history.mjs ui_revision_catalog.mjs ui_patch_import.mjs test_workbench_tools.py test_patch_import.py test_public_release.py
            test_ui_bundle.py ui_settings.mjs
            ui_startup_recovery.mjs
            test_rom_health.py ui_rom_health.mjs
            ui_startup.mjs test_ui_startup.py
            test_source_launcher.py ui_review_regressions.mjs test_regression_suite.py ui_playtest_view.mjs test_workflow_recipes.py test_memory_watches.py test_runtime_library.py test_live_playtest.py ui_audio_live.mjs
            test_help_workflows.py ui_project_flow.mjs test_resource_discovery.py test_data_tables.py ui_tables.mjs test_resource_compression.py ui_compression.mjs test_resource_exports.py ui_pixel_tools.mjs ui_pixel_history.mjs ui_tilemap_editor.mjs
            mock_libretro.c test_cd_cli.py test_cd_patch.py test_cd_reference.py
            test_cdrom.py test_oracle_execution.py test_qa_execution.py
            test_source_package.py test_verification_safety.py fixtures/mode1_vectors.json
            test_history.py test_history_cli.py test_contracts.py test_contracts_cli.py
            test_audio_capture.py test_runtime_worker.py test_runtime_workspace.py mock_worker_hang.c
            test_capture_cli.py test_capture_ingest.py test_capture_runtime.py
            test_capture_search.py test_capture_store.py script_fixtures.py
            test_script.py test_script_cli.py test_script_patch.py test_script_schema.py
            layout_fixtures.py menu_fixtures.py test_dialogue_layout.py
            test_font_metrics.py test_layout_cli.py test_menu.py test_menu_cli.py
            test_menu_compare.py test_menu_metrics.py test_menu_schema.py
            asset_fixtures.py test_asset_codecs.py test_asset_schema.py test_assets.py
            test_audio_export.py test_audio_export_runtime.py test_runtime_memory.py
            debug_fixtures.py test_debug.py test_debug_schema.py test_debug_runtime.py
            test_engineering_cli.py test_workbench_projects.py test_replay.py
            test_analysis_v50.py test_player_docs.py test_release_v50.py
            test_workbench_api.py test_workbench_jobs.py test_v50_hardening.py
            test_release_review.py test_resource_catalog.py test_windows_package.py test_streaming_release.py test_gameboy.py test_gameboy_color.py test_v52_projects.py test_v53_containers.py test_resource_forms.py test_runtime_profiles.py test_system_addresses.py test_route_editor.py test_system_registry.py test_system_identify.py
            test_v51_workflow.py
            test_system_resources.py
            test_systems_cli.py test_system_ui.py
        ''',
        'tools': '''
            build_cores.py package_cores.py fetch_cores.py package_installer.py fetch_installer.py verify_engines.py
            fetch_runtime.py audit_release.py check_ui.mjs
            build_ui.mjs
            verify_v1.py
            build_master_cheat_code_archive.py check_cd_reference.py package_source.py
            verify_v50.py package_v50.py verify_v51.py verify_v60.py package_windows.py install_windows.py
        ''',
    }.items()
    for name in names.split() if directory != 'docs'
})


APPROVED_FILES = APPROVED_FILES | frozenset({
    'romancer/ui/clean_preview.js','tests/ui_clean_preview.mjs','romancer/export_names.py','tests/test_export_names.py',
    'romancer/ui/workspace_search.js','tests/ui_workspace_search.mjs','romancer/ui/change_summary.js','tests/ui_change_summary.mjs',
    'romancer/ui/build_details.js','tests/ui_build_details.mjs','romancer/ui/brush_colors.js','tests/ui_brush_colors.mjs','romancer/ui/visual_comparison.js','tests/ui_visual_comparison.mjs',
    'user-guide/ROMancer-v1.0-Walkthrough.mp4','user-guide/walkthrough.en.vtt',
    'romancer/ui/artifact_selection.js','tests/ui_artifact_selection.mjs','romancer/ui/build_handoff.js','romancer/ui/overview_tasks.js','tests/ui_build_handoff.mjs','tests/ui_overview_tasks.mjs','tests/ui_sprite_zoom.mjs','tests/ui_guide_search.mjs','user-guide/guide.js',
    'romancer/observation_series.py','romancer/investigation_tools.py',
    'romancer/native_debugger.py','romancer/debugger_protocol.py','romancer/debugger_capture.lua',
    'romancer/debugger_tools.py','tests/test_debugger_tools.py',
    'romancer/genesis_debugger.py','romancer/genesis_capture.lua','tests/test_genesis_debugger.py',
    'romancer/structural_lab.py','romancer/structure_tools.py','tests/test_structural_lab.py','tests/test_structure_tools.py',
    'romancer/compression_oracle.py',
    'romancer/debugger_provision.py','tests/test_debugger_provision.py',
    'romancer/data_relocation.py','tests/test_data_relocation.py',
    'romancer/ui/data_relocation.js','tests/ui_data_relocation.mjs',
    'romancer/core_memory_layout.py','tests/test_core_memory_layout.py',
    'tests/test_native_debugger.py',
    'romancer/ui/investigation_series.js','tests/ui_investigation_series.mjs',
    'romancer/ui/execution_trace.js','tests/ui_execution_trace.mjs',
    'romancer/ui/structural_lab.js','tests/ui_structural_lab.mjs',
    'tests/test_observation_series.py','tests/test_investigation_tools.py',
    'romancer/cartridge_startup.py','romancer/cartridge_integrity.py','romancer/ui/cartridge_verification.js',
    'tests/test_cartridge_startup.py','tests/test_cartridge_integrity.py','tests/ui_cartridge_verification.mjs','tests/ui_hex_comparison.mjs',
    'romancer/hardware_reference.py','romancer/ui/hardware_reference.js',
    'tests/test_hardware_reference.py','tests/ui_hardware_reference.mjs',
    'romancer/cheat_decode.py','romancer/cheat_catalog.py','romancer/engine_recognition.py',
    'romancer/ui/cheat_clues.js','romancer/ui/engine_findings.js',
    'tests/test_cheat_decode.py','tests/test_cheat_catalog.py','tests/test_engine_recognition.py',
    'tests/test_cheat_scan_api.py','tests/ui_cheat_clues.mjs','tests/ui_engine_findings.mjs',
    'romancer/chrono_tables.py','romancer/ffl2_maps.py','romancer/game_knowledge.py',
    'romancer/ui/game_maps.js','tests/test_chrono_tables.py','tests/ui_chrono_tables.mjs',
    'tests/test_ffl2_maps.py','tests/test_known_maps_api.py','tests/test_game_knowledge.py','tests/ui_game_maps.mjs',
    'romancer/verified_room.py','romancer/ui/room_editor.js',
    'romancer/ui/room_navigation.js','tests/ui_level_rooms.mjs',
    'tests/test_declared_workbench.py','tests/test_investigation_mcp.py',
    'tests/ui_debug_navigation.mjs','tests/ui_memory_watch_scope.mjs',
    'tests/test_verified_room.py','tests/test_workbench_evidence.py','tests/test_user_guide.py','tests/ui_interface_scale.mjs',
    'tests/ui_room_editor.mjs','tests/ui_sound_live_preview.mjs','tests/ui_asset_pagination.mjs',
    'tests/ui_level_visual_tools.mjs','tests/ui_menu_preview.mjs','romancer/ui/menu_preview.js',
    'romancer/app_settings.py','romancer/ui/app_settings.js','tests/test_app_settings.py','tests/ui_app_settings.mjs','tests/ui_scan_preferences.mjs',
    'tools/build_user_guide.py','user-guide/index.html','user-guide/guide.css','user-guide/guide.pdf','user-guide/guide.json',
    *('user-guide/screenshots/'+name+'.png' for name in (
        '70-emerald-species-editor','71-ultraviolet-move-editor','72-automatic-table-discovery','73-reviewed-rebalance-build','74-reviewed-move-build','75-symbol-address-navigation','65-resource-research','66-research-pack-review','67-popular-game-references','68-documented-stat-prefix','69-research-byte-help',
        '01-workspace','02-castlevania-sprite','03-chrono-weapon','04-chrono-table',
        '05-immortal-text','06-wario-palettes','07-ffl2-room','08-dejavu-colors',
        '09-playtest-states','10-verified-patch','11-hex-inspection',
        '13-settings','14-light-theme','15-dark-theme','16-connected-rooms',
        '17-object-inspector','18-byte-explanation','19-chrono-armor','20-ffl2-map-browser','21-game-knowledge',
        '22-engine-recognition','23-address-domains','24-code-references','25-cartridge-verification','26-mod-byte-comparison','27-crc-mismatch','28-text-overflow','29-audio-preview','30-project-recovery','26-universal-value-series','27-native-access-capture','28-native-source-context','29-structural-experiments','30-generated-table-editor','31-debugger-preparation','32-data-relocation','33-moved-table','34-menu-contrast','35-first-workshop-edit','36-patch-compatibility-preview','37-task-workspace','38-sprite-preview','39-build-handoff','40-light-workspace','41-guide-search','45-changes-only','46-brush-build-review','47-search-files','48-readable-download','49-palette-difference','50-clean-level-comparison','51-rastan-enemy-editor','52-rastan-blobs-playtest','53-rastan-verified-patch','54-rastan-original-playtest','55-snes-visible-playtest')),
})


APPROVED_FILES = APPROVED_FILES | frozenset({'tests/test_connected_mcp.py', 'user-guide/screenshots/80-connected-room-preview.png', 'romancer/ui/trace_controls.js', 'tests/test_build_checks.py', 'romancer/build_checks.py', 'tests/test_gameplay_traces.py', 'tests/ui_trace_controls.mjs', 'user-guide/screenshots/79-genesis-automatic-build-check.png', 'romancer/connected_game.py', 'user-guide/screenshots/78-nes-gameplay-trace.png', 'tests/test_connected_game.py', 'tests/ui_connected_game.mjs', 'tests/ui_build_checks.mjs', 'romancer/ui/views/gameview.js', 'romancer/ui/build_checks.js', 'romancer/gameplay_traces.py', 'tests/ui_connected_handoffs.mjs', 'tests/test_batched_video.py'})

APPROVED_FILES = APPROVED_FILES | frozenset(['romancer/replay_journal.py', 'romancer/ui/source_verification.js', 'romancer/visual_source.py', 'romancer/visual_source_tools.py', 'tests/test_replay_journal.py', 'tests/test_visual_source.py', 'tests/test_visual_source_mcp.py', 'tests/test_visual_source_tools.py', 'tests/ui_source_verification.mjs', 'user-guide/screenshots/86-real-sms-verified-source-editor.png', 'user-guide/screenshots/87-nes-verified-source.png', 'user-guide/screenshots/88-nes-exact-pixel-byte-origins.png'])
APPROVED_FILES = APPROVED_FILES | frozenset({'romancer/object_workbench.py','romancer/graphics_snapshot.py','romancer/graphics_access.py','romancer/ui/object_workbench.js','tests/ui_object_workbench.mjs','tests/test_object_workbench.py','tests/test_graphics_snapshot.py','tests/test_graphics_access.py'})

APPROVED_FILES = APPROVED_FILES | frozenset(['romancer/bundled_debuggers.py', 'romancer/observer_pins.py', 'tests/test_bundled_debuggers.py', 'tests/test_sms_controller_native.py', 'romancer/ui/graphics_access.js', 'romancer/ui/edit_checks.js', 'tests/ui_graphics_access.mjs', 'tests/ui_edit_checks.mjs'])

APPROVED_FILES = APPROVED_FILES | frozenset({'tools/patches/mesen-graphics.patch','tools/patches/blastem-sms-input.patch'})

APPROVED_FILES = APPROVED_FILES | frozenset({'tests/test_native_source_patches.py'})

APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/screenshots/90-connected-whole-object.png', 'user-guide/screenshots/91-native-graphics-memory.png', 'user-guide/screenshots/92-captured-edit-comparison.png', 'user-guide/screenshots/93-compression-capacity.png'])


APPROVED_FILES = APPROVED_FILES | frozenset(['romancer/debugger_failures.py', 'romancer/editing_readiness.py', 'romancer/scene_composite.py', 'romancer/studio_workshop.py', 'romancer/ui/editing_readiness.js', 'tests/test_compact_guide.py', 'tests/test_debugger_failures.py', 'tests/test_editing_readiness.py', 'tests/test_scene_composite.py', 'tests/test_studio_workshop.py', 'tests/test_no_inapp_tutorials.py', 'tests/ui_editing_readiness.mjs', 'tools/compact_guide.py'])

APPROVED_FILES = APPROVED_FILES | frozenset({'tests/test_studio_systems.py'})
APPROVED_FILES = APPROVED_FILES | frozenset({'user-guide/screenshots/'+name+'.png' for name in ('220-five-editing-tools-ready','221-collision-brushes-and-live-preview','222-independent-actor-hitbox-controls','223-native-collision-lab-playtest','224-original-melody-edit-and-preview','225-wario-decoded-note-edit-and-preview','226-conditional-song-read-only')})

# Build37 reviewed guide captures
APPROVED_FILES = APPROVED_FILES | frozenset({'romancer/level_semantics.py','romancer/studio_runtime.py','romancer/m4a_music.py','romancer/format_readiness.py','romancer/ui/level_semantics.js','romancer/ui/music_sequence.js','tests/test_level_semantics.py','tests/test_studio_runtime.py','tests/test_m4a_music.py','tests/test_format_readiness.py','tests/ui_level_semantics.mjs','tests/ui_music_sequence.mjs'})

# Build37 reviewed guide captures
APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/screenshots/100-welcome-guide-only.png', 'user-guide/screenshots/101-editing-readiness.png', 'user-guide/screenshots/102-studio-sprite-editor.png', 'user-guide/screenshots/103-studio-sprite-staged.png', 'user-guide/screenshots/104-studio-dialogue-preview.png', 'user-guide/screenshots/105-studio-level-object-editor.png', 'user-guide/screenshots/106-studio-named-values.png', 'user-guide/screenshots/107-help-user-guide.png', 'user-guide/screenshots/108-verified-full-scene-preview.png'])

# Build38 reviewed source modules and regression tests
APPROVED_FILES = APPROVED_FILES | frozenset(['romancer/draft_scene.py', 'romancer/ui/draft_scene.js', 'romancer/ui/graphics_formats.js', 'tests/test_draft_scene.py', 'tests/ui_draft_scene.mjs', 'tests/ui_build_continuation.mjs', 'tests/ui_release_context.mjs', 'tests/ui_plain_language.mjs'])

APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/ACCEPTANCE.txt', 'user-guide/screenshots/200-native-palette-draft-preview.png', 'user-guide/screenshots/201-native-preview-restored.png', 'user-guide/screenshots/202-export-correct-build.png', 'user-guide/screenshots/203-measured-palette-build-playtest.png', 'user-guide/screenshots/204-recorded-workflow-after-reopen.png'])

APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/screenshots/205-original-workshop-readiness.png', 'user-guide/screenshots/206-workshop-edit-undo-redo.png', 'user-guide/screenshots/207-workshop-build-playtest.png'])

APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/screenshots/210-two-clear-starting-choices.png', 'user-guide/screenshots/211-what-can-i-edit.png', 'user-guide/screenshots/212-clear-draft-preview.png', 'user-guide/screenshots/213-paused-game-save-state.png', 'user-guide/screenshots/214-explicit-original-build-export.png'])

APPROVED_FILES = APPROVED_FILES | frozenset({
    'romancer/investigation_follow.py','romancer/definition_builder.py','romancer/reference_survey.py',
    'romancer/command_editor.py','romancer/connected_details.py','romancer/animation_layouts.py','romancer/m4a_instruments.py',
    'romancer/ui/investigation_follow.js','romancer/ui/definition_builder.js','romancer/ui/compression_references.js',
    'romancer/ui/command_editor.js','romancer/ui/saved_animations.js','romancer/ui/music_instruments.js',
    'tests/test_investigation_follow.py','tests/test_definition_builder.py','tests/test_reference_survey.py',
    'tests/test_command_editor.py','tests/test_animation_layouts.py','tests/test_m4a_controls.py','tests/test_project_studio_validation.py',
    'tests/ui_investigation_follow.mjs','tests/ui_definition_builder.mjs','tests/ui_compression_references.mjs',
    'tests/ui_command_editor.mjs','tests/ui_saved_animations.mjs','tests/ui_music_instruments.mjs',
})

APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/screenshots/230-native-writer-evidence-summary.png', 'user-guide/screenshots/231-visual-editor-builder-named-fields.png', 'user-guide/screenshots/232-wario-command-parameter-review.png', 'user-guide/screenshots/233-wario-pan-and-instrument-inspection.png', 'user-guide/screenshots/234-saved-two-pose-animation.png', 'user-guide/screenshots/235-connected-saved-animation.png', 'user-guide/screenshots/236-compressed-graphics-two-pointer-review.png', 'user-guide/screenshots/237-compact-compression-review.png', 'user-guide/screenshots/238-compact-command-editor.png'])

APPROVED_FILES = APPROVED_FILES | frozenset(['romancer/ui/build_reuse.js','tests/ui_reopen_handoff.mjs','tests/ui_build_reuse.mjs','romancer/snes_lz2.py', 'romancer/format_library.py', 'romancer/text_growth.py', 'romancer/command_rewrite.py', 'romancer/ui/format_library.js', 'romancer/ui/text_growth.js', 'romancer/ui/command_forms.js', 'romancer/ui/command_sequence.js', 'romancer/ui/navigation.js', 'tests/test_snes_lz2.py', 'tests/test_format_library.py', 'tests/test_text_growth.py', 'tests/test_command_rewrite.py', 'tests/test_debugger_focus.py', 'tests/test_theme_readability.py', 'tests/ui_format_library.mjs', 'tests/ui_text_growth.mjs', 'tests/ui_command_sequence.mjs', 'tests/ui_basic_advanced.mjs'])

APPROVED_FILES = APPROVED_FILES | frozenset(['user-guide/screenshots/240-brighter-green-basic-workspace.png', 'user-guide/screenshots/241-longer-dialogue-pointer-preview.png', 'user-guide/screenshots/242-relocated-text-reopened.png', 'user-guide/screenshots/243-longer-dialogue-native-playtest.png', 'user-guide/screenshots/244-source-bound-format-library.png', 'user-guide/screenshots/245-arranged-command-sequence-review.png', 'user-guide/screenshots/246-command-format-form.png', 'user-guide/screenshots/247-native-access-stop-registers.png', 'user-guide/screenshots/248-snes-lz2-stream-inspection.png', 'user-guide/screenshots/249-readable-theme-and-advanced-settings.png', 'user-guide/screenshots/250-compact-basic-settings.png', 'user-guide/screenshots/251-light-settings-current.png', 'user-guide/screenshots/252-dark-settings-current.png'])

def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _stream_member(source, limit, destination=None, *, require_lf=False):
    digest = hashlib.sha256()
    count = 0
    # One extra byte distinguishes exact-budget EOF from an oversized source.
    while data := source.read(min(READ_CHUNK_BYTES, limit - count + 1)):
        count += len(data)
        if count > limit:
            raise ValueError('source package byte budget exceeded')
        if require_lf and b'\r' in data:
            raise ValueError('shell launcher must use LF line endings')
        if destination is not None:
            destination.write(data)
        digest.update(data)
    return count, digest.hexdigest()


def readme_path(root: Path) -> Path:
    candidate=root/'README.txt'
    if not candidate.exists() and root.name=='app' and (root.parent/'BUNDLE.json').is_file():
        candidate=root.parent/'README.txt'
    if candidate.is_symlink() or candidate.is_junction() or not candidate.is_file():
        raise ValueError('source root lacks README.txt')
    return candidate


def package(root: Path, output: Path) -> dict:
    root = root.resolve()
    readme=readme_path(root)
    check_output_paths(readme, [output])
    output = output.absolute()
    if not (root / 'romancer' / '__init__.py').is_file():
        raise ValueError('source root lacks README.txt or romancer/__init__.py')
    members = [] if readme.parent==root else [(readme,'README.txt',readme.stat())]
    for parent, directories, names in os.walk(root, followlinks=False):
        path = Path(parent)
        directories[:] = sorted(name for name in directories if name.casefold() not in EXCLUDED
                                 and (path != root or name in DIRECTORIES))
        for name in directories:
            candidate = path / name
            if candidate.is_symlink() or candidate.is_junction():
                raise ValueError(f'linked source directory not permitted: {candidate}')
        for name in sorted(names):
            if path == root and name not in ROOT_FILES:
                continue
            if name=='memory_observations_README.txt' and path==root/'examples/runtime':continue
            candidate = path / name
            if candidate.is_symlink() or candidate.is_junction() or not candidate.is_file():
                raise ValueError(f'non-regular source member: {candidate}')
            if candidate.relative_to(root).as_posix() not in APPROVED_FILES:
                raise ValueError(f'unapproved source member: {candidate}')
            info = candidate.stat()
            if info.st_size > MAX_MEMBER_BYTES:
                raise ValueError('source member exceeds 16 MiB')
            members.append((candidate, candidate.relative_to(root).as_posix(), info))
    if len(members) > 10000 or sum(info.st_size for _, _, info in members) > MAX_TOTAL_BYTES:
        raise ValueError('source package budget exceeded')
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.romancer-package-', dir=output.parent)
    temporary = Path(name)
    os.close(descriptor)
    manifest = []
    consumed = 0
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path, relative, selected in members:
                entry = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = ((0o100755 if relative == 'run.sh' else 0o100644) << 16)
                with path.open('rb') as source, archive.open(entry, 'w') as destination:
                    opened = os.fstat(source.fileno())
                    count, member_digest = _stream_member(
                        source, min(MAX_MEMBER_BYTES, MAX_TOTAL_BYTES - consumed), destination,
                        require_lf=relative == 'run.sh')
                    if _identity(opened) != _identity(os.fstat(source.fileno())):
                        raise ValueError(f'source member changed while reading: {path}')
                consumed += count
                manifest.append({'path': relative, 'bytes': count, 'sha256': member_digest})
        with zipfile.ZipFile(temporary) as archive:
            for row in manifest:
                with archive.open(row['path']) as source:
                    count, member_digest = _stream_member(source, row['bytes'])
                if count != row['bytes'] or member_digest != row['sha256']:
                    raise ValueError('ZIP member digest mismatch')
        digest = hashlib.sha256()
        with temporary.open('rb') as source:
            while data := source.read(READ_CHUNK_BYTES):
                digest.update(data)
        for path, _, selected in members:
            if (path.is_symlink() or path.is_junction()
                    or _identity(path.stat()) != _identity(selected)):
                raise ValueError(f'source member changed before publication: {path}')
        os.link(temporary, output)
        return {'ok': True, 'scope': 'selected_source_package', 'path': str(output),
                'sha256': digest.hexdigest(), 'members': manifest,
                'note': 'Source selection and byte integrity only; not game certification.'}
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.root, args.output), indent=2))


if __name__ == '__main__':
    main()
