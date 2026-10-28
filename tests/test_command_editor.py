import hashlib,unittest

def sample():
    raw=b'\x10\x08\x20\x12\x34\xff'+b'\0'*10
    d={'schema_version':1,'source_sha256':hashlib.sha256(raw).hexdigest(),'name':'Original event format',
       'scripts':[{'id':'door','name':'Door event','offset':0,'length':8}],
       'commands':[{'opcode':16,'name':'Set health','length':2,'role':'action','fields':[{'name':'Health','offset':1,'bytes':1,'endian':'little','minimum':1,'maximum':99,'target_base':None}]},
       {'opcode':32,'name':'Go to room','length':3,'role':'room','fields':[{'name':'Destination','offset':1,'bytes':2,'endian':'big','minimum':0,'maximum':65535,'target_base':None}]},
       {'opcode':255,'name':'Finish','length':1,'role':'end','fields':[]}]}
    return raw,d

class CommandTests(unittest.TestCase):
    def test_known_grammar_decodes_named_commands_and_plans_only_fixed_operands(self):
        from romancer.command_editor import inspect_commands,plan_commands
        raw,d=sample();doc=inspect_commands(raw,d,d['source_sha256']);self.assertTrue(doc['scripts'][0]['editable'])
        self.assertEqual(doc['scripts'][0]['commands'][1]['fields'][0]['value'],0x1234)
        change={'script_id':'door','command_index':0,'field':'Health','before':8,'after':12}
        plan=plan_commands(raw,d,doc['document_id'],[change],d['source_sha256'])
        self.assertEqual(plan['edits'],[{'offset':1,'before':'08','after':'0c'}]);self.assertFalse(doc['game_semantics_verified'])
        for bad in ({**change,'field':'opcode'},{**change,'before':7},{**change,'after':True},{**change,'after':100}):
            with self.assertRaises(ValueError):plan_commands(raw,d,doc['document_id'],[bad],d['source_sha256'])
    def test_unknown_truncated_missing_end_and_overlap_stay_read_only_or_refuse(self):
        from romancer.command_editor import inspect_commands,plan_commands
        import copy
        raw,d=sample()
        for data in (b'\x11'+raw[1:],raw[:3]):
            definition=copy.deepcopy(d);definition['scripts'][0]['length']=len(data);sha=hashlib.sha256(data).hexdigest();definition['source_sha256']=sha
            doc=inspect_commands(data,definition,sha);self.assertFalse(doc['scripts'][0]['editable']);self.assertTrue(doc['scripts'][0]['issues'])
        d['commands'][1]['fields'].append({**d['commands'][1]['fields'][0],'name':'Overlap'})
        with self.assertRaises(ValueError):inspect_commands(raw,d,d['source_sha256'])
    def test_source_document_and_bounded_scripts_are_mandatory(self):
        from romancer.command_editor import inspect_commands,plan_commands
        raw,d=sample()
        with self.assertRaises(ValueError):inspect_commands(raw,d,'0'*64)
        with self.assertRaises(ValueError):plan_commands(raw,d,'0'*64,[],d['source_sha256'])

    def test_graph_parent_identity_uses_script_id_and_extent_even_for_duplicate_labels(self):
        from romancer.connected_details import extend_graph
        from pathlib import Path
        import tempfile,copy
        raw,d=sample();raw=raw+raw;d=copy.deepcopy(d);d['source_sha256']=hashlib.sha256(raw).hexdigest();d['scripts'].append({**d['scripts'][0],'id':'other','offset':16})
        nodes=[{'id':'first','kind':'commands','name':'Door event','offset':0,'length':8,'locator':None},{'id':'second','kind':'commands','name':'Door event','offset':16,'length':8,'locator':None}];edges=[]
        def add(kind,name,offset,length,editor,locator):
            n={'id':str(len(nodes)),'kind':kind,'name':name,'offset':offset,'length':length,'locator':locator};nodes.append(n);return n
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data';path.write_bytes(raw);row={'sha256':d['source_sha256'],'size':len(raw)}
            extend_graph(row,path,{'commands':d},nodes,add,lambda a,b,r:edges.append((a['id'],b['id'],r)),lambda:False)
        self.assertEqual(nodes[0]['locator'],{'script_id':'door'});self.assertEqual(nodes[1]['locator'],{'script_id':'other'})
        self.assertEqual(len([e for e in edges if e[0]=='first' and e[2]=='contains_command']),3)
        self.assertEqual(len([e for e in edges if e[0]=='second' and e[2]=='contains_command']),3)

    def test_api_saved_command_grammar_build_and_connected_graph_on_seven_systems(self):
        from pathlib import Path
        import tempfile
        from romancer.boot_fixtures import make_boot_fixture
        from romancer.workbench_api import WorkbenchAPI
        folder=self.enterContext(tempfile.TemporaryDirectory())
        api=WorkbenchAPI(Path(folder)/'work');self.addCleanup(api.close)
        settings=api.dispatch('settings.get',{});api.dispatch('settings.save',{'revision':settings['revision'],'values':{**settings['values'],'autoDeepScan':False}})
        for system in ('nes','snes','genesis','sms','gb','gbc','gba'):
            with self.subTest(system=system):
                data,d=sample();boot=bytearray(32768) if system=='sms' else bytearray(make_boot_fixture(system)['data']);
                if system=='sms':boot[0x7ff0:0x7ff8]=b'TMR SEGA';boot[0x7fff]=0x4c
                boot[0x1000:0x1006]=data[:6]
                original=Path(folder)/(system+'.'+{'genesis':'bin','snes':'sfc'}.get(system,system));original.write_bytes(boot)
                project=api.dispatch('project.create',{'name':system});source=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(original),'system':None});self.assertTrue(source['ok'],source)
                p={'project_id':project['project_id'],'artifact_id':source['artifact_id']};d['source_sha256']=source['sha256'];d['scripts'][0]['offset']=0x1000
                review=api.dispatch('definitions.preview',{**p,'kind':'commands','config':d});self.assertTrue(review['ok'],review)
                self.assertTrue(api.dispatch('definitions.save',{**p,'kind':'commands','config':d,'review_id':review['review_id'],'replace':False})['ok'])
                graph=api.dispatch('gameview.graph',{**p,'query':'','kind':'command','page':0});self.assertTrue(graph['ok'],graph)
                self.assertEqual(len(graph['nodes']),3);node=graph['nodes'][0];detail=api.dispatch('gameview.detail',{**p,'node_id':node['id']});self.assertEqual(detail['preview']['fields'][0]['value'],8)
                plan=api.dispatch('commands.plan',{**p,'definition':d,'document_id':review['inspection']['document_id'],'changes':[{'script_id':'door','command_index':0,'field':'Health','before':8,'after':12}]});self.assertTrue(plan['ok'],plan)
                build=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':plan['plan_id']});self.assertTrue(build['ok'],build)
                self.assertEqual(original.read_bytes(),bytes(boot));self.assertEqual(Path(build['path']).read_bytes()[0x1001],12)
