import hashlib
import importlib.util
import unittest


class StructuralLabTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.structural_lab'),'Universal structural experiments are missing')
        from romancer import structural_lab
        return structural_lab

    def source(self):
        raw=bytearray(b'\xff'*512)
        for i,target in enumerate((256,272,288,304,320)):
            raw[3+i*8:7+i*8]=(0x08000000+target).to_bytes(4,'little')
            raw[target:target+6]=b'HELLO\0'
        return bytes(raw)

    def survey(self,raw,system='gba',**kwargs):
        return self.module().survey(raw,hashlib.sha256(raw).hexdigest(),system,0,len(raw),**kwargs)

    def chosen(self,result):
        return next(c for c in result['candidates'] if c['offset']==3 and c['width']==4 and c['stride']==8 and c['base']==0x08000000 and c['endian']=='little')

    def test_unaligned_record_run_has_observed_values_and_no_invented_semantics(self):
        r=self.survey(self.source());c=self.chosen(r)
        self.assertEqual(c['count'],5);self.assertEqual(c['samples'][0]['target_offset'],256)
        self.assertEqual(c['samples'][0]['target_preview'],'HELLO')
        self.assertEqual(c['confidence'],'CANDIDATE');self.assertFalse(r['dereference_observed'])
        self.assertFalse(r['write_authorized']);self.assertNotIn('health',str(c).lower())

    def test_definition_is_checked_numeric_by_default_and_pointer_interpretation_is_explicit(self):
        raw=self.source();m=self.module();c=self.chosen(self.survey(raw))
        numeric=m.table_definition(c,len(raw),'numeric');self.assertIsNone(numeric['fields'][0]['pointer_base'])
        pointers=m.table_definition(c,len(raw),'linear-pointer');self.assertEqual(pointers['fields'][0]['pointer_base'],0x08000000)
        self.assertEqual(pointers['stride'],8);self.assertEqual(pointers['count'],5)
        with self.assertRaises(ValueError):m.table_definition(c,len(raw),'verified-monster-stats')
        with self.assertRaises(ValueError):m.table_definition({**c,'count':1000},len(raw),'numeric')

    def test_flat_padding_short_false_headers_and_out_of_range_values_do_not_form_a_run(self):
        for raw in (bytes(128),b'\xff'*128,(0x08000040).to_bytes(4,'little')+b'\xff'*124):
            with self.subTest(raw=raw[:8]):self.assertEqual(self.survey(raw)['candidates'],[])
        raw=b''.join((0x0f000000+i).to_bytes(4,'little') for i in range(32))
        # These words are invalid GBA ROM-window pointers. Other numeric layouts
        # in the same bytes remain hypotheses rather than a negative oracle.
        self.assertFalse(any(c['width']==4 and c['stride']==4 and c['offset']==0 and c['endian']=='little'
            for c in self.survey(raw)['candidates']))

    def test_all_six_systems_test_file_offset_hypotheses_without_a_game_profile(self):
        for system in ('nes','snes','genesis','gb','gbc','gba'):
            raw=b''.join(t.to_bytes(2,'big') for t in (64,80,96,112))+b'\xff'*120
            r=self.survey(raw,system)
            self.assertTrue(any(c['offset']==0 and c['width']==2 and c['endian']=='big' for c in r['candidates']),system)
            self.assertFalse(r['game_profile_required'])

    def test_identity_budgets_sampling_and_cancellation_are_explicit(self):
        raw=self.source();r=self.survey(raw,max_positions=32,max_results=2)
        self.assertLessEqual(len(r['candidates']),2);self.assertEqual(r['coverage']['position_stride'],16)
        with self.assertRaises(KeyboardInterrupt):self.survey(raw,cancelled=lambda:True)
        with self.assertRaises(ValueError):self.survey(bytes(65537))
        changed=bytearray(raw);changed[-1]=0
        self.assertNotEqual(self.chosen(self.survey(raw))['candidate_id'],self.chosen(self.survey(bytes(changed)))['candidate_id'])
