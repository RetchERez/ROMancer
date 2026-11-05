"""Known engine recognition and explicit gaps, separate from scan candidates."""
from .studio_runtime import matches_studio_runtime,make_collision_studio_rom,runtime_definitions

def checked_formats(raw, sha, descriptors):
    result = {'engine': None, 'features': [], 'native_playtest_verified': False, 'write_authorized': False}
    if matches_studio_runtime(raw):
        result['engine'] = {'id': 'mossy-runtime-v1', 'name': 'Mossy Hollow original runtime', 'evidence': 'Immutable original program matches. Editing layouts are checked separately.'}
        definitions = runtime_definitions(make_collision_studio_rom(), sha)
        checks = {}
        for kind in ('levels', 'sound'):
            try:
                if kind == 'levels':
                    from .level_design import inspect_level
                    inspect_level(raw, definitions[kind], sha)
                else:
                    from .sound_studio import inspect_sound
                    inspect_sound(raw, definitions[kind], sha)
                checks[kind] = None
            except (ValueError, KeyError, TypeError) as error:
                checks[kind] = str(error)
        for ident, name, page in [('collision', 'Movement & collision', 'levels'), ('hitboxes', 'Actor hitboxes & damage', 'levels'), ('movement', 'Enemy movement & patrol', 'levels'), ('music', 'Original melody', 'sound')]:
            problem = checks['sound' if page == 'sound' else 'levels']
            result['features'].append({'id': ident, 'name': name, 'status': 'needs_repair' if problem else 'checked_layout', 'page': page, 'action': 'Inspect source values' if problem else 'Open editor', 'detail': problem or 'Original runtime uses these declared fields. Build and playtest to verify your change.'})
        result['suggested_definitions'] = definitions
    levels = descriptors.get('levels') if type(descriptors) is dict else None
    if not result['engine'] and type(levels) is dict:
        try:
            from .level_design import inspect_level
            doc = inspect_level(raw, levels, sha)
            for ident, name, available in [('collision', 'Collision grid', any((r['collision'] is not None for r in doc['rooms']))), ('hitboxes', 'Actor rectangles', any((m.get('hitbox') for r in doc['rooms'] for m in r.get('object_metadata', []))))]:
                result['features'].append({'id': ident, 'name': name, 'status': 'declared_layout' if available else 'needs_investigation', 'page': 'levels', 'action': 'Open layout' if available else 'Investigate the layout', 'detail': 'Declared layout can be edited; gameplay meaning requires independent evidence.' if available else 'No supported mapping is saved for this feature.'})
        except (ValueError, KeyError, TypeError):
            pass
    from .release_scope import LEVEL_EDITOR_ENABLED
    if not LEVEL_EDITOR_ENABLED:
        result['features'] = [item for item in result['features'] if item['page'] != 'levels']
    return result
