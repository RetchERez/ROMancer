"""Literal synthetic layout oracles; no native renderer or font assumptions."""
import copy
import importlib
import importlib.util
import itertools
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.layout_fixtures import layout_fixture, digest_json
from romancer import script


class DialogueLayoutTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.dialogue_layout'),
                             'dialogue layout service not implemented')
        self.layout = importlib.import_module('romancer.dialogue_layout')
        self.temp = tempfile.TemporaryDirectory(prefix='dialogue layout ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.font_path = self.root / 'source.bin', self.root / 'font.bin'
        self.fixture([b'SORRY FOR', b'THE WAIT!'], 102)

    def fixture(self, lines, width, **kwargs):
        self.raw, self.font, self.schema, self.font_schema, self.policy = layout_fixture(lines, width, **kwargs)
        self.source.write_bytes(self.raw)
        self.font_path.write_bytes(self.font)

    def rebind(self):
        import hashlib
        self.schema['artifact']['size'] = len(self.raw)
        self.schema['profile']['accepted_sha256'] = [hashlib.sha256(self.raw).hexdigest()]
        for rule in self.schema['profile']['rules']:
            rule['expected_hex'] = self.raw[rule['offset']:rule['offset']+rule['length']].hex()
        self.policy['script_schema_sha256'] = digest_json(self.schema)
        self.policy['font_schema_sha256'] = digest_json(self.font_schema)
        self.policy['document_id'] = digest_json(dict(parser_version=1,
            schema_sha256=digest_json(self.schema), source_sha256=hashlib.sha256(self.raw).hexdigest(),
            source_size=len(self.raw)))
        self.source.write_bytes(self.raw)
        self.font_path.write_bytes(self.font)

    def check(self):
        return self.layout.check_layout(self.source, self.schema, self.font_path, self.font_schema, self.policy)

    def plan(self, editorial=None, checked=None):
        checked = checked or self.check()
        request = dict(schema_version=1, analysis_id=checked['analysis_id'], editorial_replacements=editorial or [])
        return self.layout.plan_layout(self.source, self.schema, self.font_path, self.font_schema, self.policy, request)

    def lines(self, geometry):
        return [line for page in geometry['records'][0]['pages'] for line in page['lines']]

    def test_literal_sentence_collapse_preserves_full_slot_and_controls(self):
        checked = self.check()
        self.assertTrue(checked['ok'], checked)
        self.assertEqual([x['advance_px'] for x in self.lines(checked['analysis'])], [51, 48])
        proposed = self.plan(checked=checked)
        self.assertTrue(proposed['ok'], proposed)
        self.assertEqual([x['text'] for x in self.lines(proposed['candidate'])], ['SORRY FOR THE WAIT!', ''])
        self.assertEqual([x['advance_px'] for x in self.lines(proposed['candidate'])], [102, 0])
        compiled = script.plan_script(self.source, self.schema, proposed['script_edits'])
        self.assertEqual(compiled['plan_id'], proposed['script_plan_id'])
        self.assertEqual(bytes.fromhex(compiled['final_records'][0]['raw_hex']),
                         b'SORRY FOR THE WAIT!\xe1\0'+b'\xff'*7)
        self.assertEqual(proposed['candidate']['records'][0]['pages'][0]['reserved_height_px'], 10)
        self.assertFalse(proposed['native_render_verified'])
        self.assertEqual(proposed['break_deltas'][0]['text_byte_delta'], 1)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(self.font_path.read_bytes(), self.font)

    def test_three_lines_and_already_empty_suffix(self):
        self.fixture([b'ARE THERE', b'ORKS UP', b'AHEAD?'], 129)
        plan = self.plan()
        self.assertTrue(plan['ok'], plan)
        self.assertEqual([x['text'] for x in self.lines(plan['candidate'])], ['ARE THERE ORKS UP AHEAD?', '', ''])
        compiled = script.plan_script(self.source, self.schema, plan['script_edits'])
        self.assertEqual(bytes.fromhex(compiled['final_records'][0]['raw_hex']),
                         b'ARE THERE ORKS UP AHEAD?\xe1\xe1\0'+b'\xff'*6)
        self.fixture([b'SORRY FOR THE WAIT!', b''], 102)
        plan = self.plan()
        self.assertEqual(plan['status'], 'NO_CHANGES', plan)
        self.assertEqual(plan['script_edits']['changes'], [])

    def test_left_fill_and_orphan_priority_literal_widths(self):
        for before, width, after, advances in [([b'AA A A', b'A A A'], 40, ['AA A A A', 'A A'], [39, 15]),
                                              ([b'AAA BB', b'B'], 33, ['AAA', 'BB B'], [18, 21])]:
            with self.subTest(before=before):
                self.fixture(before, width)
                result = self.plan()
                self.assertTrue(result['ok'], result)
                self.assertEqual([x['text'] for x in self.lines(result['candidate'])], after)
                self.assertEqual([x['advance_px'] for x in self.lines(result['candidate'])], advances)

    def test_no_padding_prevents_collapsing_but_does_not_remove_control(self):
        self.fixture([b'SORRY FOR', b'THE WAIT!'], 102, padding=0)
        result = self.plan()
        self.assertTrue(result['ok'], result)
        self.assertEqual([x['text'] for x in self.lines(result['candidate'])], ['SORRY FOR THE', 'WAIT!'])
        self.assertTrue(any(x['code'] == 'CAPACITY_CONSTRAINT' for x in result['candidate']['diagnostics']))
        self.assertEqual(result['candidate']['records'][0]['padding_bytes'], 0)

    def test_shared_record_byte_winner_is_group_b(self):
        self.fixture([b'AAA', b'BBB', b'AAAA', b'A'], 40, padding=1)
        self.raw = self.raw.replace(b'BBB\xe1AAAA', b'BBB\xe2AAAA')
        self.schema['format']['controls'].append(dict(id='page', opcode=226, argument_length=0,
            position_independent=True, layout_role='page'))
        self.policy['controls'].append(dict(control_id='page', arguments_hex='', effect='page_reset',
            provenance=copy.deepcopy(self.policy['provenance'])))
        self.policy['records'][0]['breaks'] = [self.policy['records'][0]['breaks'][i] for i in (0, 2)]
        self.rebind()
        result = self.plan()
        self.assertTrue(result['ok'], result)
        self.assertEqual([x['text'] for x in self.lines(result['candidate'])], ['AAA', 'BBB', 'AAAA A', ''])
        compiled = script.plan_script(self.source, self.schema, result['script_edits'])
        self.assertEqual(bytes.fromhex(compiled['final_records'][0]['raw_hex']), b'AAA\xe1BBB\xe2AAAA A\xe1\0')

    def test_intentional_and_unknown_breaks_are_not_soft(self):
        self.policy['records'][0]['breaks'][0].update(intent='intentional', joiner=None)
        result = self.plan()
        self.assertEqual(result['status'], 'NO_CHANGES', result)
        self.assertEqual(result['candidate']['quality_status'], 'NOT_APPLICABLE')
        self.policy['records'][0]['breaks'][0]['intent'] = 'unknown'
        checked = self.check()
        self.assertEqual(checked['analysis']['quality_status'], 'BLOCKED')
        self.assertFalse(self.plan(checked=checked)['ok'])

    def test_geometry_ink_advance_blank_and_height(self):
        for lines, width, height, bearing, expected in [([b'A'], 6, 5, 0, True),
                    ([b'A'], 5, 5, 0, False), ([b'A'], 6, 4, 0, False),
                    ([b'A'], 6, 5, -1, False), ([b'  '], 5, 5, 0, False),
                    ([b'A', b''], 6, 5, 0, False)]:
            with self.subTest(lines=lines, width=width, height=height, bearing=bearing):
                self.fixture(lines, width)
                self.policy['boxes'][0]['height_px'] = height
                next(g for g in self.font_schema['glyphs'] if g['id'] == 'g65')['bearing']['x'] = bearing
                self.rebind()
                result = self.check()
                self.assertIs(result['ok'], expected, result)
                self.assertEqual(result['analysis']['geometry_status'], 'PASS' if expected else 'FAIL')

    def test_automatic_reflow_does_not_trim_or_cross_interior_empty(self):
        for lines in ([b'A ', b'B'], [b'A  B', b'C'], [b'A', b'', b'B'], [b'A', b' ']):
            with self.subTest(lines=lines):
                self.fixture(lines, 50)
                checked = self.check()
                self.assertEqual(checked['analysis']['geometry_status'], 'PASS')
                result = self.plan(checked=checked)
                self.assertFalse(result['ok'], result)
                self.assertFalse(result.get('script_edits'))

    def test_all_empty_remains_unchanged_and_reserves_lines(self):
        self.fixture([b'', b''], 20)
        result = self.plan()
        self.assertEqual(result['status'], 'NO_CHANGES', result)
        self.assertEqual([x['text'] for x in self.lines(result['candidate'])], ['', ''])
        self.assertEqual(result['candidate']['records'][0]['pages'][0]['reserved_height_px'], 10)

    def test_editorial_is_explicit_bound_and_recorded(self):
        editorial = [dict(record_id='a', segment=0, before_text='SORRY FOR', after_text='THANKS FOR',
                          rationale='Reviewed wording', review_reference='review fixture 1')]
        result = self.plan(editorial)
        self.assertTrue(result['ok'], result)
        self.assertEqual([x['text'] for x in self.lines(result['candidate'])], ['THANKS FOR THE', 'WAIT!'])
        self.assertEqual(result['editorial_deltas'], editorial)
        editorial[0]['review_reference'] = ''
        self.assertFalse(self.plan(editorial)['ok'])

    def test_unknown_policy_authority_and_duplicate_keys_reject(self):
        for mutate in (lambda p: p['controls'].append(copy.deepcopy(p['controls'][0])),
                       lambda p: p['glyph_map'].pop(),
                       lambda p: p['records'][0]['breaks'].append(copy.deepcopy(p['records'][0]['breaks'][0])),
                       lambda p: p['controls'][0].update(arguments_hex='00'),
                       lambda p: p.update(verified=True)):
            self.fixture([b'A', b'B'], 20)
            mutate(self.policy)
            with self.subTest(policy=self.policy), self.assertRaises(ValueError):
                self.layout.validate_layout_policy(self.policy, self.schema, self.font_schema)

    def test_stale_analysis_and_font_do_not_produce_edits(self):
        checked = self.check()
        self.policy['boxes'][0]['width_px'] -= 1
        self.assertFalse(self.plan(checked=checked)['ok'])
        self.font_path.write_bytes(b'x'+self.font[1:])
        result = self.check()
        self.assertFalse(result['ok'])

    def test_wrap_warning_has_actual_capacity_valid_witness(self):
        result = self.check()
        witnesses = [d['witness'] for d in result['analysis']['diagnostics'] if d['code'] == 'AVOIDABLE_WRAP']
        self.assertEqual(witnesses, [dict(before=['SORRY FOR', 'THE WAIT!'], after=['SORRY FOR THE WAIT!', ''], text_byte_delta=1)])
        self.assertTrue(result['ok'])

    def shared_capacity_witness_case(self, padding):
        self.fixture([b'AAA BBB', b'', b'AAAA', b'A'], 40, padding=padding)
        self.raw = self.raw.replace(b'\xe1\xe1AAAA', b'\xe1\xe2AAAA')
        self.schema['format']['controls'].append(dict(id='page', opcode=226, argument_length=0,
            position_independent=True, layout_role='page'))
        self.policy['controls'].append(dict(control_id='page', arguments_hex='', effect='page_reset',
            provenance=copy.deepcopy(self.policy['provenance'])))
        self.policy['records'][0]['breaks'] = [self.policy['records'][0]['breaks'][i] for i in (0, 2)]
        self.rebind()
        checked = self.check()
        proposed = self.plan(checked=checked)
        self.assertTrue(checked['ok'], checked)
        self.assertTrue(proposed['ok'], proposed)
        doc = script.inspect_script(self.source, self.schema)
        edits = dict(schema_version=1, document_id=doc['document_id'],
            source_sha256=doc['source_sha256'], schema_sha256=doc['schema_sha256'],
            changes=[dict(record_id='a', segment=2, text='AAAA A'),
                     dict(record_id='a', segment=3, text='')])
        standalone = script.plan_script(self.source, self.schema, edits)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(self.font_path.read_bytes(), self.font)
        return checked, proposed, standalone

    def test_wrap_witness_cannot_spend_undisplayed_compensating_reflow(self):
        checked, proposed, standalone = self.shared_capacity_witness_case(padding=0)
        self.assertFalse(standalone['ok'], standalone)
        self.assertEqual(standalone['error_code'], 'CAPACITY')
        self.assertEqual([line['text'] for line in self.lines(proposed['candidate'])],
                         ['AAA', 'BBB', 'AAAA A', ''])
        compiled = script.plan_script(self.source, self.schema, proposed['script_edits'])
        self.assertTrue(compiled['ok'], compiled)
        self.assertEqual(bytes.fromhex(compiled['final_records'][0]['raw_hex']),
                         b'AAA\xe1BBB\xe2AAAA A\xe1\0')
        for geometry in (checked['analysis'], proposed['before']):
            self.assertFalse([d for d in geometry['diagnostics'] if d['code'] == 'AVOIDABLE_WRAP'])

    def test_wrap_witness_with_own_spare_byte_still_compiles_independently(self):
        checked, proposed, standalone = self.shared_capacity_witness_case(padding=1)
        self.assertTrue(standalone['ok'], standalone)
        self.assertEqual(bytes.fromhex(standalone['final_records'][0]['raw_hex']),
                         b'AAA BBB\xe1\xe2AAAA A\xe1\0')
        for geometry in (checked['analysis'], proposed['before']):
            witnesses = [d for d in geometry['diagnostics'] if d['code'] == 'AVOIDABLE_WRAP']
            self.assertEqual(len(witnesses), 1)
            self.assertEqual((witnesses[0]['page_index'], witnesses[0]['line_index']), (1, 0))
            self.assertEqual(witnesses[0]['witness'], dict(
                before=['AAAA', 'A'], after=['AAAA A', ''], text_byte_delta=1))

    def test_exact_pause_arguments_do_not_move_words_or_authorize_other_variants(self):
        self.fixture([b'A\xe3\x01B', b'C'], 40)
        self.schema['format']['controls'].append(dict(id='pause', opcode=227, argument_length=1,
            position_independent=True, layout_role='pause'))
        prov = copy.deepcopy(self.policy['provenance'])
        self.policy['controls'].extend([dict(control_id='pause', arguments_hex=args,
            effect='pause_no_motion', provenance=prov) for args in ('01', '02')])
        self.policy['records'][0]['breaks'][0]['control_index'] = 1
        self.rebind()
        result = self.plan()
        self.assertEqual(result['status'], 'NO_CHANGES', result)
        self.assertEqual([l['text'] for l in self.lines(result['candidate'])], ['AB', 'C'])
        self.assertEqual(result['candidate']['quality_status'], 'NOT_APPLICABLE')
        self.assertEqual([g['x'] for g in self.lines(result['candidate'])[0]['glyphs']], [0, 6])
        self.policy['controls'] = [r for r in self.policy['controls'] if r['arguments_hex'] != '01']
        checked = self.check()
        self.assertFalse(checked['ok'], checked)
        self.assertEqual(checked['analysis']['geometry_status'], 'BLOCKED')
        self.assertFalse(self.plan(checked=checked)['ok'])

    def test_unselected_opaque_record_preserves_check_but_blocks_complete_compiler(self):
        target = len(self.raw)-4
        self.raw = self.raw[:-4] + b'\xfe\0\xff\xff' + target.to_bytes(2, 'little')
        self.schema['profile']['rules'].extend([
            dict(resource='opaque-slot', offset=target, length=4, expected_hex='fe00ffff'),
            dict(resource='other-pointer', offset=target+4, length=2, expected_hex=target.to_bytes(2, 'little').hex())])
        self.schema['format']['records'].append(dict(id='b', rule='opaque-slot',
            annotations=copy.deepcopy(self.schema['format']['records'][0]['annotations'])))
        self.schema['format']['pointers'].append(dict(id='pb', rule='other-pointer', target_record='b',
            width=2, endian='little', base=0))
        self.rebind()
        checked = self.check()
        self.assertTrue(checked['ok'], checked)
        self.assertFalse(checked['document_write_supported'])
        self.assertFalse(checked['proposal_supported'])
        with patch.object(script, 'compile_changes', wraps=script.compile_changes) as compile_call:
            result = self.plan(checked=checked)
        self.assertFalse(result['ok'], result)
        self.assertEqual([r['id'] for r in compile_call.call_args.args[0]['records']], ['a', 'b'])
        self.assertTrue(compile_call.call_args.args[0]['read_only_reasons'])
        self.policy['records'][0]['record_id'] = 'b'
        self.policy['records'][0]['breaks'] = []
        checked = self.check()
        self.assertFalse(checked['ok'])
        self.assertEqual(checked['analysis']['records'][0]['pages'], [])

    def test_long_word_and_punctuation_require_actual_feasible_partition(self):
        for lines, width in [([b'SHADOWRUNNERS'], 20), ([b'A', b'!'], 6), ([b'(', b'A'], 6)]:
            with self.subTest(lines=lines):
                self.fixture(lines, width)
                checked = self.check()
                self.assertFalse(checked['ok'], checked)
                result = self.plan(checked=checked)
                self.assertFalse(result['ok'], result)
                self.assertIsNone(result['script_edits'])

    def test_editorial_capacity_and_pixel_overflow_remain_distinct(self):
        checked = self.check()
        edit = dict(record_id='a', segment=0, before_text='SORRY FOR', after_text='A'*40,
                    rationale='Explicit supplied edit', review_reference='review')
        result = self.plan([edit], checked)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'CAPACITY')
        edit['after_text'] = 'A'*15
        self.policy['boxes'][0]['width_px'] = 20
        result = self.plan([edit])
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'NO_FEASIBLE_LAYOUT')

    def test_final_cross_check_keeps_both_handles_open_and_blocks_changes(self):
        original = self.layout._assert_inputs
        seen = []
        def inspect(inputs):
            seen.append([stream for _, stream, _ in inputs])
            self.assertEqual(len(inputs), 2)
            self.assertTrue(all(not stream.closed for _, stream, _ in inputs))
            original(inputs)
        with patch.object(self.layout, '_assert_inputs', side_effect=inspect):
            result = self.plan()
        self.assertTrue(result['ok'], result)
        self.assertGreaterEqual(len(seen), 4)
        self.assertTrue(all(stream.closed for pair in seen for stream in pair))
        for which in ('font', 'source'):
            self.fixture([b'A', b'B'], 20)
            checked = self.check()
            def changing(inputs):
                if changing.calls:
                    path = self.font_path if which == 'font' else self.source
                    data = path.read_bytes()
                    path.write_bytes(bytes([data[0] ^ 1])+data[1:])
                changing.calls += 1
                original(inputs)
            changing.calls = 0
            with self.subTest(which=which), patch.object(self.layout, '_assert_inputs', side_effect=changing):
                result = self.plan(checked=checked)
            self.assertFalse(result['ok'], result)
            self.assertEqual(result['error']['code'], 'SOURCE_CHANGED')
            self.assertIsNone(result['script_edits'])

    def test_cancellation_closes_inputs_without_usable_edits(self):
        checked = self.check()
        streams = []
        original = self.layout._assert_inputs
        def observe(inputs):
            streams.extend(stream for _, stream, _ in inputs)
            original(inputs)
        with patch.object(self.layout, '_assert_inputs', side_effect=observe), \
                patch.object(self.layout, '_optimize', side_effect=KeyboardInterrupt):
            result = self.plan(checked=checked)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertTrue(streams)
        self.assertTrue(all(s.closed for s in streams))
        self.assertIsNone(result['script_edits'])

    def test_operation_budgets_block_without_partial_edits(self):
        checked = self.check()
        for constant in ('MAX_PLACEMENTS', 'MAX_INTERVALS', 'MAX_TRANSITIONS', 'MAX_PAGES', 'MAX_LINES'):
            with self.subTest(constant=constant), patch.object(self.layout, constant, 0):
                result = self.plan(checked=checked)
            self.assertFalse(result['ok'], result)
            self.assertEqual(result['error']['code'], 'BUDGET')
            self.assertIsNone(result['script_edits'])
            self.assertNotIn('candidate', result)

    def test_malformed_public_requests_return_bounded_errors(self):
        for request in ({}, [], None, dict(schema_version=1, analysis_id='0'*64),
                        dict(schema_version=True, analysis_id='0'*64, editorial_replacements=[])):
            with self.subTest(request=request):
                result = self.layout.plan_layout(self.source, self.schema, self.font_path, self.font_schema, self.policy, request)
                self.assertFalse(result['ok'])
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertFalse(result.get('script_edits'))

    def test_actual_group_and_combined_placement_limits_refuse(self):
        for lines, width in (([b' '.join([b'A']*128), b'A'], 1024),
                             ([b'A']*17, 1024), ([b'A'*130]*8, 1024)):
            self.fixture(lines, width)
            with self.subTest(line_count=len(lines), text_bytes=sum(map(len, lines))):
                result = self.plan()
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['error']['code'], 'BUDGET')
                self.assertIsNone(result['script_edits'])
                self.assertNotIn('candidate', result)

    def test_invalid_control_effect_type_is_a_validation_error(self):
        for effect in ({}, [], True, None):
            self.policy['controls'][0]['effect'] = effect
            with self.subTest(effect=effect), self.assertRaises(ValueError):
                self.layout.validate_layout_policy(self.policy, self.schema, self.font_schema)

    def test_result_budget_failure_is_still_bounded_public_error(self):
        checked = self.check()
        with patch.object(self.layout, 'MAX_REPORT', 3000):
            result = self.plan(checked=checked)
        self.assertFalse(result['ok'])
        self.assertIsNone(result['script_edits'])

    def test_soft_joiner_requires_encodable_space(self):
        self.fixture([b'A', b'B'], 20)
        self.schema['format']['encoding']['glyphs'] = [g for g in self.schema['format']['encoding']['glyphs'] if g['byte'] != 32]
        self.policy['glyph_map'] = [g for g in self.policy['glyph_map'] if g['byte'] != 32]
        self.rebind()
        with self.assertRaises(ValueError):
            self.layout.validate_layout_policy(self.policy, self.schema, self.font_schema)
        self.assertFalse(self.check()['ok'])

    def test_small_exhaustive_partition_oracle_matches_actual_proposals(self):
        before = [b'AA A', b'AAA', b'A A']
        words = ['AA', 'A', 'AAA', 'A', 'A']
        original_breaks = (2, 3)
        for width, padding in itertools.product((18, 21, 24, 30, 39, 60), (0, 1, 2)):
            options = []
            for k in range(1, 4):
                for cuts in itertools.combinations(range(1, len(words)), k-1):
                    ends = (*cuts, len(words))
                    starts = (0, *cuts)
                    texts = [' '.join(words[a:b]) for a, b in zip(starts, ends)] + ['']*(3-k)
                    advances = [sum(3 if c == ' ' else 6 for c in text) for text in texts]
                    if max(advances) > width or sum(map(len, texts)) > sum(map(len, before))+padding:
                        continue
                    orphan = int(k >= 2 and len(texts[k-1].split(' ')) <= 1 and advances[k-1]*100 <= width*25)
                    breaks = (*cuts, *(len(words) for _ in range(3-k)))
                    cost = (k, orphan, tuple(-i for i in breaks), sum(abs(a-b) for a, b in zip(breaks, original_breaks)))
                    options.append((cost, texts))
            self.fixture(before, width, padding=padding)
            with self.subTest(width=width, padding=padding):
                result = self.plan()
                if not options:
                    self.assertFalse(result['ok'], result)
                else:
                    self.assertTrue(result['ok'], result)
                    self.assertEqual([l['text'] for l in self.lines(result['candidate'])], min(options)[1])

    def test_identical_input_ids_stable_and_declaration_changes_invalidate(self):
        before = self.check()
        first = self.plan(checked=before)
        self.assertEqual(first['proposal_id'], self.plan(checked=before)['proposal_id'])
        self.assertEqual(before['analysis_id'], self.check()['analysis_id'])
        for change in ('mapping', 'advance', 'source', 'tool'):
            self.fixture([b'A', b'B'], 20)
            checked = self.check()
            if change == 'mapping':
                a = next(g for g in self.policy['glyph_map'] if g['byte'] == 65)
                b = next(g for g in self.policy['glyph_map'] if g['byte'] == 66)
                a['glyph_id'], b['glyph_id'] = b['glyph_id'], a['glyph_id']
            elif change == 'advance':
                glyph = next(g for g in self.font_schema['glyphs'] if g['id'] == 'g65')
                glyph['advance'] = dict(kind='declared', pixels=5, provenance=copy.deepcopy(self.policy['provenance']))
                self.rebind()
            elif change == 'source':
                self.raw = self.raw.replace(b'A\xe1B', b'B\xe1A')
                self.rebind()
            if change == 'tool':
                with patch.object(self.layout, 'ROMANCER_VERSION', 'fixture-next'):
                    result = self.plan(checked=checked)
            else:
                result = self.plan(checked=checked)
            with self.subTest(change=change):
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['error']['code'], 'STALE_ANALYSIS')

    def test_refuses_links_and_unsupported_layout_without_creating_files(self):
        before = set(self.root.iterdir())
        self.policy['model'] = 'future-layout'
        self.assertFalse(self.check()['ok'])
        self.policy['model'] = 'explicit-lines-v1'
        self.font_schema['codec'] = 'future-codec'
        self.rebind()
        self.assertFalse(self.check()['ok'])
        self.assertEqual(set(self.root.iterdir()), before)
        self.fixture([b'A', b'B'], 20)
        linked = self.root / 'linked-font'
        try:
            linked.symlink_to(self.font_path)
        except OSError as exc:
            self.skipTest(f'file symlinks unavailable: {exc}')
        result = self.layout.check_layout(self.source, self.schema, linked, self.font_schema, self.policy)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'UNSAFE_PATH')

    def test_raw_drive_relative_inputs_reject_before_any_open(self):
        for spelling in ('C:source.bin', 'c:.\\source.bin', 'C:..\\source.bin', 'C:'):
            for field in ('source', 'font'):
                source = spelling if field == 'source' else self.source
                font = spelling if field == 'font' else self.font_path
                with self.subTest(spelling=spelling, field=field), patch.object(
                        Path, 'open', side_effect=AssertionError('ambiguous input must never open')):
                    result = self.layout.check_layout(source, self.schema, font, self.font_schema, self.policy)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error']['code'], 'UNSAFE_PATH')


if __name__ == '__main__':
    unittest.main()
