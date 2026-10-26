"""Synthetic data only: exercise names, field boundaries and guarded edits."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

from romancer import data_tables


class ChronoTableTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.chrono_tables'),
                             'named source-decoded rebalance definitions are missing')
        from romancer import chrono_tables
        return chrono_tables

    def test_names_are_decoded_from_selected_revision_and_keep_stable_ids(self):
        service=self.service()
        resource=next(r for r in service.resource_definitions() if r['id']=='weapon-stats-table')
        config=resource['definition']
        raw=bytearray(0x400000)
        # Original synthetic labels, not game text. Icon + "Axe 2" + padding.
        raw[0xc0b69:0xc0b74]=bytes.fromhex('20a0d1beffd6efefefefef')
        raw[0xc0267:0xc026c]=bytes([17,91,35,202,203])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.sfc';path.write_bytes(raw)
            sha=hashlib.sha256(raw).hexdigest()
            result=data_tables.inspect_table(path,sha,config,0,1)
            row=result['rows'][0]
            self.assertEqual((row['label'],row['record_id'],row['label_status']),('Axe 2',1,'decoded'))
            self.assertEqual(result['row_catalog'][0]['label'],'Axe 2')
            edits=data_tables.table_edits(path,sha,config,[{'row':0,'field':'Base attack','before':17,'after':25},
                {'row':0,'field':'Critical rate (%)','before':35,'after':100}])
            self.assertEqual(edits,[{'offset':0xc0267,'before':'11','after':'19'},
                                    {'offset':0xc0269,'before':'23','after':'64'}])
            self.assertEqual(path.read_bytes(),raw)
            raw[0xc0b6a]=0xa1;path.write_bytes(raw)
            changed=data_tables.inspect_table(path,hashlib.sha256(raw).hexdigest(),config,0,1)
            self.assertEqual(changed['rows'][0]['label'],'Bxe 2')
            self.assertNotEqual(changed['document_id'],result['document_id'])
            with self.assertRaisesRegex(ValueError,'revision changed'):
                data_tables.inspect_table(path,sha,config)

    def test_defined_defense_price_and_enemy_edits_touch_only_supported_fields(self):
        service=self.service();resources={r['id']:r for r in service.resource_definitions()}
        raw=bytearray(0x400000)
        raw[0xc0481:0xc0484]=bytes([12,177,178])
        raw[0xc06a4+6*0x5b:0xc06a4+6*0x5b+6]=bytes.fromhex('c53412c6c7c8')
        raw[0xc4700:0xc4717]=bytes(range(23))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            cases=[('armor-defense-table',{'row':0,'field':'Base defense','before':12,'after':23},
                    [{'offset':0xc0481,'before':'0c','after':'17'}]),
                   ('armor-price-table',{'row':0,'field':'Base price','before':4660,'after':600},
                    [{'offset':0xc08c7,'before':'3412','after':'5802'}]),
                   ('enemy-core-stats-table',{'row':0,'field':'HP','before':256,'after':513},
                    [{'offset':0xc4700,'before':'0001','after':'0102'}])]
            for key,change,want in cases:
                self.assertEqual(data_tables.table_edits(path,sha,resources[key]['definition'],[change]),want)
            self.assertEqual(path.read_bytes(),raw)

    def test_unsupported_and_blank_labels_are_honest_and_enemy_garbage_is_excluded(self):
        service=self.service()
        self.assertEqual(service.decode_name(bytes.fromhex('a0efa1efef')),{'label':'A B','label_status':'decoded'})
        self.assertEqual(service.decode_name(b'\xef'*11),{'label':'Blank slot','label_status':'blank'})
        result=service.decode_name(bytes([0xa0,0x00,0x80]))
        self.assertEqual(result['label_status'],'unsupported')
        self.assertIn('[00]',result['label']);self.assertIn('[80]',result['label'])
        resources={r['id']:r for r in service.resource_definitions()}
        self.assertEqual([resources[k]['definition']['count'] for k in
            ('weapon-stats-table','armor-defense-table','helm-defense-table')],[85,32,24])
        self.assertEqual(resources['enemy-core-stats-table']['definition']['count'],251)

    def test_legacy_weapon_resource_keeps_original_numeric_row_indices(self):
        resources={r['id']:r for r in self.service().resource_definitions()}
        legacy=resources['weapon-power-table'];self.assertTrue(legacy['legacy'])
        config=legacy['definition']
        self.assertEqual((config['offset'],config['count'],config['stride']),(0xc0262,90,5))
        self.assertNotIn('label_source',config)
        self.assertEqual([field['name'] for field in config['fields']],['Base attack'])


class DeclaredLabelAndLimitTests(unittest.TestCase):
    def config(self):
        return {'schema_version':1,'name':'Synthetic entries','offset':0,'count':2,'stride':2,
                'fields':[{'name':'Chance','offset':0,'type':'u8','endian':'little','pointer_base':None,
                           'minimum':0,'maximum':100}],
                'label_source':{'offset':4,'stride':4,'length':4,'skip':0,'encoding':'chrono-name','id_base':9}}

    def test_limits_reject_edits_and_batches_but_allow_repair_of_invalid_old_values(self):
        raw=bytes([150,99,30,98,0xa0,0xef,0xef,0xef,0xa1,0xef,0xef,0xef])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();config=self.config()
            result=data_tables.inspect_table(path,sha,config)
            self.assertEqual(result['rows'][0]['cells'][0]['value'],150)
            self.assertEqual(result['rows'][1]['record_id'],10)
            self.assertEqual(data_tables.table_edits(path,sha,config,[{'row':0,'field':'Chance','before':150,'after':100}]),
                             [{'offset':0,'before':'96','after':'64'}])
            for after in (-1,101,True):
                with self.assertRaises(ValueError):
                    data_tables.table_edits(path,sha,config,[{'row':1,'field':'Chance','before':30,'after':after}])
            with self.assertRaisesRegex(ValueError,'row 1'):
                data_tables.batch_changes(path,sha,config,'Chance','add',80,1,1)

    def test_invalid_label_ranges_and_numeric_limits_fail_closed(self):
        import copy
        config=self.config()
        for mutate in (lambda d:d['label_source'].update(offset=11),
                       lambda d:d['label_source'].update(encoding='unknown'),
                       lambda d:d['label_source'].update(skip=4),
                       lambda d:d['fields'][0].update(maximum=256),
                       lambda d:d['fields'][0].update(minimum=101),
                       lambda d:d.update(row_labels=['stale','labels'])):
            bad=copy.deepcopy(config);mutate(bad)
            with self.assertRaises(ValueError):data_tables.validate_definition(bad,12)


if __name__=='__main__':unittest.main()
