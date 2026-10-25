"""Advisory explicit-line layout from held script bytes and supplied font metrics."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat

from . import ROMANCER_VERSION, script
from .font_metrics import validate_font_schema, measure_font_stream
from .script_schema import canonical_bytes, validate_schema

MAX_JSON = 1024 * 1024
MAX_REPORT = 8 * 1024 * 1024
MAX_PLACEMENTS = 2048
MAX_INTERVALS = 16384
MAX_TRANSITIONS = 262144
MAX_PAGES = 64
MAX_LINES = 256


class LayoutError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _fail(code, message):
    raise LayoutError(code, message)


def _snapshot(value, maximum=MAX_JSON):
    return json.loads(canonical_bytes(value, max_bytes=maximum))


def _digest(value):
    return hashlib.sha256(canonical_bytes(value, max_bytes=MAX_REPORT)).hexdigest()


def _fields(value, names):
    if type(value) is not dict or set(value) != set(names.split()):
        _fail('FIELDS', 'missing or unexpected layout fields')


def _integer(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        _fail('BOUNDS', 'integer outside layout bounds')


def _label(value, limit=128):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)):
        _fail('LABEL', 'invalid bounded label')


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        _fail('IDENTITY', 'expected lowercase SHA-256')


def _list(value, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail('BOUNDS', 'list outside layout bounds')


def _provenance(value):
    _fields(value, 'origin note reference')
    if value['origin'] not in ('profile_assertion', 'synthetic_fixture'):
        _fail('PROVENANCE', 'unknown declaration origin')
    _label(value['note'], 512)
    if value['reference'] is not None:
        _label(value['reference'], 256)


def validate_layout_policy(policy: dict, script_schema: dict, font_schema: dict) -> dict:
    policy = _snapshot(policy)
    sv, fv = validate_schema(script_schema), validate_font_schema(font_schema)
    _fields(policy, 'schema_version id version model document_id script_schema_sha256 font_schema_sha256 glyph_map boxes controls records quality provenance')
    _integer(policy['schema_version'], 1, 1)
    for key in ('id', 'version', 'model'):
        _label(policy[key])
    for key in ('document_id', 'script_schema_sha256', 'font_schema_sha256'):
        _hash(policy[key])
    if policy['script_schema_sha256'] != sv['schema_sha256'] or policy['font_schema_sha256'] != fv['font_schema_sha256']:
        _fail('STALE_POLICY', 'policy descriptor hashes do not match')
    _provenance(policy['provenance'])
    fmt = sv['normalized_schema']['format']
    known = fmt.get('family') == 'fixed-slots' and fmt.get('version') == 1 and fmt.get('encoding', {}).get('kind') == 'single-byte'
    reasons = [] if known else ['Unsupported script grammar has no selected parse authority.']
    if policy['model'] != 'explicit-lines-v1':
        reasons.append('Unsupported explicit layout model.')
    if not fv['measurement_supported']:
        reasons.extend(fv['read_only_reasons'])
    _list(policy['glyph_map'], 256, 1)
    mapped = set()
    glyph_ids = {g['id'] for g in fv['normalized_schema']['glyphs']}
    for row in policy['glyph_map']:
        _fields(row, 'byte glyph_id')
        _integer(row['byte'], 0, 255)
        _label(row['glyph_id'])
        if row['byte'] in mapped or row['glyph_id'] not in glyph_ids:
            _fail('GLYPH_MAP', 'duplicate byte or missing font glyph')
        mapped.add(row['byte'])
    if known and mapped != {g['byte'] for g in fmt['encoding']['glyphs']}:
        _fail('GLYPH_MAP', 'mapping must cover the exact script glyph table')
    _list(policy['boxes'], 64, 1)
    boxes = set()
    for box in policy['boxes']:
        _fields(box, 'id width_px height_px line_height_px')
        _label(box['id'])
        if box['id'] in boxes:
            _fail('BOX', 'duplicate box ID')
        boxes.add(box['id'])
        _integer(box['width_px'], 1, 1024)
        _integer(box['height_px'], 1, 1024)
        _integer(box['line_height_px'], 1, 64)
    _list(policy['controls'], 4096)
    control_keys = set()
    definitions = {c['id']: c for c in fmt.get('controls', [])} if known else {}
    roles = {'line_reset': 'line', 'page_reset': 'page', 'pause_no_motion': 'pause'}
    for row in policy['controls']:
        _fields(row, 'control_id arguments_hex effect provenance')
        _label(row['control_id'])
        args = row['arguments_hex']
        if type(args) is not str or re.fullmatch('[0-9a-f]{0,32}', args) is None or len(args) % 2:
            _fail('CONTROL', 'arguments must be bounded lowercase hex')
        key = (row['control_id'], args)
        if key in control_keys or type(row['effect']) is not str or row['effect'] not in roles:
            _fail('CONTROL', 'duplicate exact control key or unknown effect')
        control_keys.add(key)
        if known:
            declared = definitions.get(row['control_id'])
            if declared is None or len(args) != 2*declared['argument_length'] or declared['layout_role'] != roles[row['effect']]:
                _fail('CONTROL', 'control ID, exact arity, or role does not match v37')
        _provenance(row['provenance'])
    _list(policy['records'], 64, 1)
    records, used_boxes = set(), set()
    record_ids = {r['id'] for r in fmt.get('records', [])} if known else set()
    for row in policy['records']:
        _fields(row, 'record_id box_id breaks')
        _label(row['record_id'])
        _label(row['box_id'])
        if row['record_id'] in records or row['box_id'] not in boxes or (known and row['record_id'] not in record_ids):
            _fail('RECORD', 'duplicate or unbound record/box')
        records.add(row['record_id'])
        used_boxes.add(row['box_id'])
        _list(row['breaks'], 256)
        seen = set()
        for br in row['breaks']:
            _fields(br, 'control_index intent joiner provenance')
            _integer(br['control_index'], 0, 4095)
            if br['control_index'] in seen or br['intent'] not in ('soft', 'intentional', 'unknown'):
                _fail('BREAK', 'duplicate break occurrence or unknown intent label')
            seen.add(br['control_index'])
            if br['joiner'] != (' ' if br['intent'] == 'soft' else None):
                _fail('BREAK', 'only soft breaks have the literal space joiner')
            if known and br['intent'] == 'soft' and not any(g['text'] == ' ' for g in fmt['encoding']['glyphs']):
                _fail('BREAK', 'soft breaks require an encodable literal space')
            _provenance(br['provenance'])
    if boxes != used_boxes:
        _fail('BOX', 'unreferenced layout box')
    quality = policy['quality']
    _fields(quality, 'orphan_max_words orphan_max_percent forbid_line_start forbid_line_end')
    _integer(quality['orphan_max_words'], 1, 4)
    _integer(quality['orphan_max_percent'], 0, 100)
    scalars = {g['text'] for g in fmt['encoding']['glyphs']} if known else None
    for key in ('forbid_line_start', 'forbid_line_end'):
        _list(quality[key], 32)
        seen = set()
        for value in quality[key]:
            _label(value, 1)
            if value in seen or (scalars is not None and value not in scalars):
                _fail('PUNCTUATION', 'duplicate or unmapped punctuation scalar')
            seen.add(value)
    return dict(normalized_policy=policy, layout_policy_sha256=_digest(policy),
                layout_supported=not reasons, read_only_reasons=reasons)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _path(value):
    windows = PureWindowsPath(value)
    if windows.drive and not windows.root:
        _fail('UNSAFE_PATH', 'drive-relative source path')
    path = Path(value).absolute()
    if os.name == 'nt' and (os.path.isreserved(path) or str(path).replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\'))):
        _fail('UNSAFE_PATH', 'reserved or ambiguous source path')
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            _fail('UNSAFE_PATH', 'linked input ancestry')
    return path


def _assert_inputs(inputs):
    for path, stream, initial in inputs:
        _path(path)
        if _identity(path.lstat()) != initial or _identity(os.fstat(stream.fileno())) != initial:
            _fail('SOURCE_CHANGED', 'held script/font or its pathname changed')


@contextmanager
def _layout_inputs(source, script_schema, font, font_schema, policy):
    sv, fv = validate_schema(script_schema), validate_font_schema(font_schema)
    ss, fs = sv['normalized_schema'], fv['normalized_schema']
    pv = validate_layout_policy(policy, ss, fs)
    paths = ((_path(source), 64*1024*1024), (_path(font), 16*1024*1024))
    with ExitStack() as stack:
        inputs = []
        for path, limit in paths:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                _fail('SOURCE_BOUNDS', 'input must be an ordinary bounded file')
            stream = stack.enter_context(path.open('rb', buffering=0))
            inputs.append((path, stream, _identity(info)))
        _assert_inputs(inputs)
        document = script.inspect_stream(inputs[0][1], ss)
        if document['document_id'] != pv['normalized_policy']['document_id']:
            _fail('STALE_POLICY', 'policy document identity is stale')
        metrics = measure_font_stream(inputs[1][1], fs)
        if not metrics['ok']:
            error = metrics['error']
            if metrics['status'] == 'CANCELLED':
                raise KeyboardInterrupt
            _fail(error['code'], error['message'])
        context = dict(document=document, metrics=metrics, policy=pv['normalized_policy'],
                       policy_validation=pv, script_schema=ss, font_schema=fs)
        yield context
        _assert_inputs(inputs)


class _Budget:
    def __init__(self):
        self.counts = {}

    def add(self, name, limit, count=1):
        self.counts[name] = self.counts.get(name, 0) + count
        if self.counts[name] > limit:
            _fail('BUDGET', name+' budget exhausted')


def _union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _status(values):
    values = list(values)
    return next((v for v in ('BLOCKED', 'FAIL', 'PASS') if v in values), 'NOT_APPLICABLE')


def _diagnostic(code, message, row, page=None, line=None, *, severity='error', witness=None):
    return dict(code=code, severity=severity, message=message, record_id=row,
                page_index=page, line_index=line, witness=witness)


def _text_metric(text, glyphs):
    x, ink = 0, None
    for c in text:
        g = glyphs[c]
        b = g['ink_bounds']
        if b is not None:
            dx, dy = x+g['bearing']['x'], g['bearing']['y']
            ink = _union(ink, [b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy])
        x += g['advance_pixels']
    return x, ink


def _fits(metric, box, line):
    advance, ink = metric
    y = line*box['line_height_px']
    return (advance <= box['width_px'] and y+box['line_height_px'] <= box['height_px']
            and (ink is None or (ink[0] >= 0 and ink[1]+y >= 0
                 and ink[2] <= box['width_px'] and ink[3]+y <= box['height_px'])))


def _punctuation(text, quality):
    visible = text.strip(' ')
    return not visible or (visible[0] not in quality['forbid_line_start'] and visible[-1] not in quality['forbid_line_end'])


def _word_lines(texts):
    empty = False
    words, boundaries = [], []
    for text in texts:
        if text == '':
            empty = True
        elif empty or text.startswith(' ') or text.endswith(' ') or '  ' in text:
            return None
        else:
            words.extend(text.split(' '))
        boundaries.append(len(words))
    return words, tuple(boundaries[:-1])


def _orphan(texts, box, glyphs, quality):
    nonempty = [s for s in texts if s]
    return int(len(nonempty) >= 2 and len(nonempty[-1].split(' ')) <= quality['orphan_max_words']
               and _text_metric(nonempty[-1], glyphs)[0]*100 <= box['width_px']*quality['orphan_max_percent'])


def _record_model(row, selection, policy):
    controls = {(c['control_id'], c['arguments_hex']): c['effect'] for c in policy['controls']}
    breaks = {b['control_index']: b for b in selection['breaks']}
    encountered = set()
    pages = [[]]
    line = dict(index=0, page=0, segments=[], pause=False)
    pages[0].append(line)
    groups, group = [], [line]
    ordinal = segment = 0
    unknown = False
    for token in row['tokens']:
        if token['kind'] == 'text':
            line['segments'].append((segment, row['segments'][segment]['text']))
            segment += 1
        elif token['kind'] == 'control':
            key = (token['control_id'], token['arguments_hex'])
            if key not in controls:
                _fail('CONTROL_AUTHORITY', 'encountered control lacks exact effect declaration')
            effect = controls[key]
            if effect == 'pause_no_motion':
                line['pause'] = True
            else:
                soft = False
                if effect == 'line_reset':
                    if ordinal not in breaks:
                        _fail('BREAK_AUTHORITY', 'line occurrence lacks explicit intent')
                    encountered.add(ordinal)
                    intent = breaks[ordinal]['intent']
                    unknown |= intent == 'unknown'
                    soft = intent == 'soft'
                if not soft:
                    groups.append(group)
                    group = []
                if effect == 'page_reset':
                    pages.append([])
                line = dict(index=len(pages[-1]), page=len(pages)-1, segments=[], pause=False)
                pages[-1].append(line)
                group.append(line)
            ordinal += 1
    groups.append(group)
    if encountered != set(breaks):
        _fail('BREAK_AUTHORITY', 'break entry does not select a line control occurrence')
    for page in pages:
        for line in page:
            line['text'] = ''.join(s for _, s in line['segments'])
    return dict(row=row, pages=pages, groups=groups, unknown=unknown)


def _analyze(ctx, records, budget):
    policy = ctx['policy']
    fonts = {g['id']: g for g in ctx['metrics']['glyphs']}
    mapping = {g['byte']: fonts[g['glyph_id']] for g in policy['glyph_map']}
    glyphs = {g['text']: mapping[g['byte']] for g in ctx['script_schema']['format'].get('encoding', {}).get('glyphs', [])}
    byte_map = {g['text']: g['byte'] for g in ctx['script_schema']['format'].get('encoding', {}).get('glyphs', [])}
    boxes = {b['id']: b for b in policy['boxes']}
    by_id = {r['id']: r for r in records}
    geometry = dict(geometry_status='PASS', capacity_status='PASS', quality_status='NOT_APPLICABLE', records=[], diagnostics=[])
    models = []
    for selection in policy['records']:
        identifier = selection['record_id']
        row = by_id.get(identifier)
        output = dict(record_id=identifier, capacity_bytes=row['capacity'] if row else None,
                      used_bytes=row['used_bytes'] if row else None, padding_bytes=row['padding_bytes'] if row else None,
                      geometry_status='PASS', capacity_status='PASS', quality_status='NOT_APPLICABLE', pages=[])
        geometry['records'].append(output)
        if not row or row['read_only_reasons']:
            output.update(geometry_status='BLOCKED', capacity_status='BLOCKED', quality_status='BLOCKED')
            geometry['diagnostics'].append(_diagnostic('SELECTED_PARSE', 'selected record has no complete parse', identifier))
            continue
        try:
            model = _record_model(row, selection, policy)
        except LayoutError as exc:
            output.update(geometry_status='BLOCKED', quality_status='BLOCKED')
            geometry['diagnostics'].append(_diagnostic(exc.code, str(exc), identifier))
            continue
        box = boxes[selection['box_id']]
        model.update(box=box, output=output, glyphs=glyphs)
        models.append(model)
        if model['unknown']:
            output['quality_status'] = 'BLOCKED'
            geometry['diagnostics'].append(_diagnostic('UNKNOWN_INTENT', 'line intent is not authorized', identifier))
        for page_index, lines in enumerate(model['pages']):
            budget.add('pages', MAX_PAGES)
            page = dict(index=page_index, box_id=box['id'], **{k: box[k] for k in ('width_px', 'height_px', 'line_height_px')},
                        used_line_count=sum(bool(l['text']) for l in lines), reserved_line_count=len(lines),
                        reserved_height_px=len(lines)*box['line_height_px'], ink_bounds=None, lines=[])
            output['pages'].append(page)
            for line in lines:
                budget.add('lines', MAX_LINES)
                y, x, ink, placements = line['index']*box['line_height_px'], 0, None, []
                for segment, text in line['segments']:
                    for scalar, char in enumerate(text):
                        budget.add('placements', MAX_PLACEMENTS)
                        g = glyphs[char]
                        b = g['ink_bounds']
                        translated = None if b is None else [b[0]+x+g['bearing']['x'], b[1]+y+g['bearing']['y'],
                            b[2]+x+g['bearing']['x'], b[3]+y+g['bearing']['y']]
                        placements.append(dict(glyph_id=g['id'], byte=byte_map[char], text=char, segment=segment,
                            scalar=scalar, x=x, y=y, advance_px=g['advance_pixels'], ink_bounds=translated))
                        ink = _union(ink, translated)
                        x += g['advance_pixels']
                rendered = dict(index=line['index'], text=line['text'], advance_px=x, ink_bounds=ink,
                                reserved_height_px=box['line_height_px'], glyphs=placements)
                page['lines'].append(rendered)
                page['ink_bounds'] = _union(page['ink_bounds'], ink)
                errors = []
                if x > box['width_px']:
                    errors.append(('ADVANCE_OVERFLOW', 'pen extent exceeds drawable width'))
                if ink is not None and (ink[0] < 0 or ink[1] < 0 or ink[2] > box['width_px'] or ink[3] > box['height_px']):
                    errors.append(('INK_CLIPPING', 'measured ink exceeds drawable rectangle'))
                if y+box['line_height_px'] > box['height_px']:
                    errors.append(('LINE_COUNT_OVERFLOW', 'reserved line height exceeds drawable box'))
                if not _punctuation(line['text'], policy['quality']):
                    errors.append(('PUNCTUATION_BOUNDARY', 'declared punctuation boundary constraint fails'))
                if any(_text_metric(w, glyphs)[0] > box['width_px'] for w in line['text'].split(' ')):
                    errors.append(('WORD_TOO_WIDE', 'indivisible word exceeds drawable advance width'))
                for code, message in errors:
                    output['geometry_status'] = 'FAIL'
                    geometry['diagnostics'].append(_diagnostic(code, message, identifier, page_index, line['index']))
        for group in model['groups']:
            if len(group) == 1 or any(l['pause'] for l in group):
                geometry['diagnostics'].append(_diagnostic('QUALITY_NOT_APPLICABLE', 'fixed intentional/page/pause boundary excludes reflow quality',
                    identifier, group[0]['page'], group[0]['index'], severity='note'))
                continue
            texts = [l['text'] for l in group]
            if _word_lines(texts) is None:
                output['quality_status'] = 'BLOCKED'
                geometry['diagnostics'].append(_diagnostic('REFLOW_GRAMMAR', 'edge/repeated spaces or interior empty soft lines cannot be reflowed', identifier))
            elif output['quality_status'] != 'BLOCKED':
                output['quality_status'] = _status([output['quality_status'], 'PASS'])
                if _orphan(texts, box, glyphs, policy['quality']):
                    output['quality_status'] = 'FAIL'
                    last = next(l for l in reversed(group) if l['text'])
                    geometry['diagnostics'].append(_diagnostic('SHORT_ORPHAN', 'last nonempty soft line is a short orphan',
                        identifier, last['page'], last['index'], severity='warning'))
    _geometry_status(geometry)
    return geometry, models


def _geometry_status(geometry):
    for key in ('geometry_status', 'capacity_status', 'quality_status'):
        geometry[key] = _status(row[key] for row in geometry['records'])


def _option(texts, before, box, glyphs, quality, *, fixed=False):
    parsed = _word_lines(texts)
    boundaries = parsed[1] if parsed is not None else ()
    movement = sum(abs(a-b) for a, b in zip(boundaries, before))
    return dict(texts=texts, boundaries=boundaries,
                cost=(sum(bool(s) for s in texts), 0 if fixed else _orphan(texts, box, glyphs, quality),
                      tuple(-b for b in boundaries), movement, ()))


def _group_options(group, box, glyphs, quality, budget):
    texts = [l['text'] for l in group]
    if len(group) == 1 or any(l['pause'] for l in group):
        return [_option(texts, (), box, glyphs, quality, fixed=True)]
    parsed = _word_lines(texts)
    if parsed is None:
        _fail('REFLOW_GRAMMAR', 'automatic reflow cannot trim spaces or cross interior empty lines')
    words, before = parsed
    n, w = len(group), len(words)
    if n > 16 or w > 128:
        _fail('BUDGET', 'reflow group exceeds 16 lines or 128 words')
    if not words:
        return [_option(texts, before, box, glyphs, quality)]
    intervals = {}
    for start in range(w):
        for end in range(start+1, w+1):
            budget.add('intervals', MAX_INTERVALS)
            text = ' '.join(words[start:end])
            intervals[start, end] = (text, _text_metric(text, glyphs), _punctuation(text, quality))
    # A prefix state keeps the lexicographically fullest earlier boundaries.
    # Only the final line can contribute an orphan, so this is a sufficient state.
    previous = {0: ()}
    options = []
    for k in range(1, min(n, w)+1):
        current = {}
        for start, boundaries in previous.items():
            for end in range(start+1, w+1):
                budget.add('transitions', MAX_TRANSITIONS)
                text, metric, punctuation = intervals[start, end]
                if not punctuation or not _fits(metric, box, group[k-1]['index']):
                    continue
                ends = (*boundaries, end)
                if end == w:
                    if any(not _fits((0, None), box, line['index']) for line in group[k:]):
                        continue
                    starts = (0, *ends[:-1])
                    candidate = [' '.join(words[a:b]) for a, b in zip(starts, ends)] + ['']*(n-k)
                    option = _option(candidate, before, box, glyphs, quality)
                    same = next((i for i, o in enumerate(options) if o['cost'][0] == k), None)
                    if same is None:
                        options.append(option)
                    elif option['cost'] < options[same]['cost']:
                        options[same] = option
                elif end not in current or tuple(-b for b in ends) < tuple(-b for b in current[end]):
                    current[end] = ends
        previous = current
    if not options:
        _fail('NO_FEASIBLE_LAYOUT', 'no complete pixel-valid word partition exists')
    return options


def _add_cost(a, b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2], a[3]+b[3], a[4]+b[4])


def _optimize(models, quality, budget):
    chosen = []
    for model in models:
        if model['unknown']:
            _fail('UNKNOWN_INTENT', 'unknown line intent prevents a proposal')
        groups = model['groups']
        options = [_group_options(g, model['box'], model['glyphs'], quality, budget) for g in groups]
        states = {0: ((0, 0, (), 0, ()), [])}
        ideal = sum(min(o['cost'][0] for o in choices) for choices in options)
        for group, choices in zip(groups, options):
            next_states = {}
            original_size = sum(len(l['text']) for l in group)
            for delta, (cost, selected) in states.items():
                for index, option in enumerate(choices):
                    budget.add('transitions', MAX_TRANSITIONS)
                    used = delta + sum(map(len, option['texts'])) - original_size
                    combined = _add_cost(cost, option['cost'])
                    combined = (*combined[:4], (*combined[4], index))
                    if used not in next_states or combined < next_states[used][0]:
                        next_states[used] = (combined, [*selected, option])
            states = next_states
        feasible = [(cost, selected) for delta, (cost, selected) in states.items()
                    if model['row']['used_bytes']+delta <= model['row']['capacity']]
        if not feasible:
            _fail('CAPACITY', 'no complete partition fits the shared record allocation')
        cost, selected = min(feasible, key=lambda item: item[0])
        chosen.append((model, selected, cost[0] > ideal))
    return chosen


def _quality_witnesses(geometry, chosen):
    for model, options, constrained in chosen:
        row = model['output']
        if constrained:
            geometry['diagnostics'].append(_diagnostic('CAPACITY_CONSTRAINT',
                'shared slot bytes prevent the minimum pixel-feasible line count', row['record_id'], severity='note'))
        for group, option in zip(model['groups'], options):
            before = [l['text'] for l in group]
            parsed = _word_lines(before)
            if len(group) < 2 or any(l['pause'] for l in group) or parsed is None:
                continue
            old = parsed[1]
            new = option['boundaries']
            delta = sum(map(len, option['texts']))-sum(map(len, before))
            # The displayed group must fit without undisplayed changes elsewhere.
            if model['row']['used_bytes'] + delta > model['row']['capacity']:
                continue
            if all(a >= b for a, b in zip(new, old)) and any(a > b for a, b in zip(new, old)):
                geometry['diagnostics'].append(_diagnostic('AVOIDABLE_WRAP', 'authorized forward word movement has a complete feasible witness',
                    row['record_id'], group[0]['page'], group[0]['index'], severity='warning',
                    witness=dict(before=before, after=option['texts'], text_byte_delta=delta)))
                if row['quality_status'] != 'BLOCKED':
                    row['quality_status'] = 'FAIL'
    _geometry_status(geometry)


def _edits(document, changes):
    return dict(schema_version=1, **{key: document[key] for key in ('document_id', 'source_sha256', 'schema_sha256')}, changes=changes)


def _editorial(document, selected, request):
    _fields(request, 'schema_version analysis_id editorial_replacements')
    _integer(request['schema_version'], 1, 1)
    _hash(request['analysis_id'])
    _list(request['editorial_replacements'], 256)
    records = {r['id']: r for r in document['records']}
    seen, changes = set(), []
    for edit in request['editorial_replacements']:
        _fields(edit, 'record_id segment before_text after_text rationale review_reference')
        _label(edit['record_id'])
        if edit['record_id'] not in selected or edit['record_id'] not in records:
            _fail('EDITORIAL', 'editorial target is not a selected parsed record')
        segments = records[edit['record_id']]['segments']
        _integer(edit['segment'], 0, len(segments)-1)
        if type(edit['before_text']) is not str or segments[edit['segment']]['text'] != edit['before_text']:
            _fail('EDITORIAL', 'editorial before text is stale')
        if type(edit['after_text']) is not str:
            _fail('EDITORIAL', 'editorial replacement must be text')
        _label(edit['rationale'], 512)
        _label(edit['review_reference'], 256)
        key = edit['record_id'], edit['segment']
        if key in seen:
            _fail('EDITORIAL', 'duplicate editorial target')
        seen.add(key)
        changes.append(dict(record_id=edit['record_id'], segment=edit['segment'], text=edit['after_text']))
    return changes


def _verify_preservation(before, after, models):
    finals = {r['id']: r for r in after}
    for row in before:
        old = [t['raw_hex'] for t in row['tokens'] if t['kind'] in ('control', 'terminator')]
        new = [t['raw_hex'] for t in finals[row['id']]['tokens'] if t['kind'] in ('control', 'terminator')]
        if old != new:
            _fail('CONTROL_CHANGED', 'final compilation changed ordered controls or terminator')
    for model in models:
        final = finals[model['row']['id']]
        for group in model['groups']:
            original = [l['text'] for l in group]
            indices = [i for l in group for i, _ in l['segments']]
            texts = [final['segments'][i]['text'] for i in indices]
            if len(group) == 1 or any(l['pause'] for l in group):
                if texts != [s for l in group for _, s in l['segments']]:
                    _fail('BARRIER_CHANGED', 'reflow crossed a protected text boundary')
            elif _word_lines(original)[0] != _word_lines(texts)[0]:
                _fail('WORDS_CHANGED', 'reflow changed ordered post-editorial words')


def _result(operation):
    return dict(schema_version=1, layout_version=1, tool_version=ROMANCER_VERSION,
                scope='dialogue_layout', operation=operation, ok=False, status='BLOCKED',
                analysis_id=None, document_id=None, metrics_id=None, layout_policy_sha256=None,
                document_write_supported=False, proposal_supported=False, proposal_block_reasons=[],
                native_render_verified=False, written=False, warnings=[], error=None)


def _bounded(result):
    try:
        canonical_bytes(result, max_bytes=MAX_REPORT)
    except ValueError as exc:
        raise LayoutError('REPORT_LIMIT', 'layout report exceeds JSON bounds') from exc
    total = 1
    for part in json.JSONEncoder(sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2).iterencode(result):
        total += len(part)
        if total > MAX_REPORT:
            _fail('REPORT_LIMIT', 'layout report exceeds 8 MiB')
    return result


def _execute(operation, source, script_schema, font, font_schema, policy, request=None):
    result, phase = _result(operation), 'validation'
    try:
        request = _snapshot(request) if operation == 'plan' else None
        if operation == 'plan':
            _fields(request, 'schema_version analysis_id editorial_replacements')
            _integer(request['schema_version'], 1, 1)
            _hash(request['analysis_id'])
            _list(request['editorial_replacements'], 256)
        with _layout_inputs(source, script_schema, font, font_schema, policy) as ctx:
            doc, metrics, policy = ctx['document'], ctx['metrics'], ctx['policy']
            result.update(document_id=doc['document_id'], metrics_id=metrics['metrics_id'],
                          layout_policy_sha256=ctx['policy_validation']['layout_policy_sha256'],
                          document_write_supported=doc['write_supported'],
                          selected_records=[r['record_id'] for r in policy['records']], provenance=policy['provenance'])
            result['analysis_id'] = _digest(dict(layout_version=1, tool_version=ROMANCER_VERSION,
                document_id=result['document_id'], metrics_id=result['metrics_id'], layout_policy_sha256=result['layout_policy_sha256']))
            if not ctx['policy_validation']['layout_supported']:
                _fail('UNSUPPORTED_LAYOUT', '; '.join(ctx['policy_validation']['read_only_reasons']))
            budget = _Budget()
            phase = 'analysis'
            before, models = _analyze(ctx, doc['records'], budget)
            reasons = list(doc['read_only_reasons'])
            if before['geometry_status'] == 'BLOCKED' or before['quality_status'] == 'BLOCKED':
                reasons.append('Selected layout authority or reflow grammar is incomplete.')
            chosen = None
            if not reasons:
                try:
                    chosen = _optimize(models, policy['quality'], budget)
                    _quality_witnesses(before, chosen)
                except LayoutError as exc:
                    if exc.code == 'BUDGET':
                        raise
                    reasons.append(str(exc))
            result.update(proposal_supported=not reasons, proposal_block_reasons=reasons)
            if operation == 'check':
                result['analysis'] = before
                hard = _status([before['geometry_status'], before['capacity_status'],
                                'BLOCKED' if before['quality_status'] == 'BLOCKED' else 'PASS'])
                result.update(ok=hard == 'PASS', status=hard)
            else:
                result.update(before=before, candidate=None, script_edits=None, script_plan_id=None, proposal_id=None)
                if request['analysis_id'] != result['analysis_id']:
                    _fail('STALE_ANALYSIS', 'request does not match fresh analysis identity')
                phase = 'editorial'
                changes = _editorial(doc, set(result['selected_records']), request)
                # Never prune the original document, even when only some records are selected.
                editorial = script.compile_changes(doc, ctx['script_schema'], _edits(doc, changes))
                if before['geometry_status'] == 'BLOCKED':
                    _fail('LAYOUT_AUTHORITY', 'selected geometry lacks required authority')
                post = editorial['final_records']
                if changes:
                    # Internal post-editorial geometry is not emitted and consumes no placement budget.
                    post_models = []
                    for model in models:
                        row = next(r for r in post if r['id'] == model['row']['id'])
                        selection = next(s for s in policy['records'] if s['record_id'] == row['id'])
                        new = _record_model(row, selection, policy)
                        new.update(box=model['box'], glyphs=model['glyphs'], output=model['output'])
                        post_models.append(new)
                    models = post_models
                    chosen = None
                phase = 'reflow'
                if chosen is None:
                    chosen = _optimize(models, policy['quality'], budget)
                texts = {(r['id'], s['index']): s['text'] for r in post for s in r['segments']}
                for model, options, _ in chosen:
                    for group, option in zip(model['groups'], options):
                        if len(group) > 1 and not any(l['pause'] for l in group):
                            for line, text in zip(group, option['texts']):
                                texts[model['row']['id'], line['segments'][0][0]] = text
                final_changes = [dict(record_id=r['id'], segment=s['index'], text=texts[r['id'], s['index']])
                                 for r in doc['records'] for s in r['segments'] if texts[r['id'], s['index']] != s['text']]
                phase = 'compilation'
                edits = _edits(doc, final_changes)
                compiled = script.compile_changes(doc, ctx['script_schema'], edits)
                _verify_preservation(post, compiled['final_records'], models)
                candidate, _ = _analyze(ctx, compiled['final_records'], budget)
                for model, _, constrained in chosen:
                    if constrained:
                        candidate['diagnostics'].append(_diagnostic('CAPACITY_CONSTRAINT',
                            'shared bytes require more lines than pixel-only minimum', model['row']['id'], severity='note'))
                result['candidate'] = candidate
                if candidate['geometry_status'] != 'PASS' or candidate['capacity_status'] != 'PASS' or candidate['quality_status'] == 'BLOCKED':
                    _fail('NO_FEASIBLE_LAYOUT', 'all selected final records must satisfy hard layout constraints')
                result.update(ok=True, status='PROPOSED' if final_changes else 'NO_CHANGES',
                    proposal_supported=True, proposal_block_reasons=[], script_edits=edits,
                    script_plan_id=compiled['plan_id'], editorial_deltas=request['editorial_replacements'],
                    break_deltas=[dict(record_id=m['row']['id'], before=[l['text'] for l in g], after=o['texts'],
                                       text_byte_delta=sum(map(len, o['texts']))-sum(len(l['text']) for l in g))
                                  for m, opts, _ in chosen for g, o in zip(m['groups'], opts) if [l['text'] for l in g] != o['texts']],
                    changed_record_count=compiled['changed_record_count'], changed_byte_count=compiled['changed_byte_count'],
                    changed_segment_count=len(final_changes))
                result['proposal_id'] = _digest(dict(proposal_version=1, tool_version=ROMANCER_VERSION,
                    analysis_id=result['analysis_id'], normalized_request=request, script_edits=edits, script_plan_id=compiled['plan_id']))
            phase = 'result'
            _bounded(result)
        return result
    except (ValueError, OSError, KeyboardInterrupt, RecursionError) as exc:
        cancelled = isinstance(exc, KeyboardInterrupt)
        result.update(ok=False, status='CANCELLED' if cancelled else 'BLOCKED', proposal_supported=False,
                      error=dict(phase=phase, code='CANCELLED' if cancelled else getattr(exc, 'code', type(exc).__name__),
                                 message='Operation cancelled' if cancelled else str(exc)[:2048]))
        if operation == 'plan':
            result.update(script_edits=None, script_plan_id=None, proposal_id=None)
        if getattr(exc, 'code', None) in ('BUDGET', 'REPORT_LIMIT'):
            for key in ('analysis', 'before', 'candidate'):
                result.pop(key, None)
        return _bounded(result)


def check_layout(source: Path, script_schema: dict, font: Path, font_schema: dict, policy: dict) -> dict:
    return _execute('check', source, script_schema, font, font_schema, policy)


def plan_layout(source: Path, script_schema: dict, font: Path, font_schema: dict, policy: dict, request: dict) -> dict:
    return _execute('plan', source, script_schema, font, font_schema, policy, request)
