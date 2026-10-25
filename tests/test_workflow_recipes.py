import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

class RecipeTests(unittest.TestCase):
    def service(self):
        self.assertIsNotNone(importlib.util.find_spec('romancer.workflow_recipes'),'offline recipes missing')
        from romancer import workflow_recipes
        return workflow_recipes

    def recipe(self,raw):
        return {'format':'romancer-recipe-v1','name':'Original edit','source':{'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)},'operations':[{'kind':'bytes','offset':2,'before':'4344','after':'5859'}]}

    def test_repeatable_preview_and_stale_source_refusal(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';raw=b'ABCDEFGH';path.write_bytes(raw);recipe=self.recipe(raw)
            a=service.preview_recipe(path,recipe);b=service.preview_recipe(path,recipe)
            self.assertEqual(a,b);self.assertEqual(a['edits'],[{'offset':2,'before':'4344','after':'5859'}]);self.assertEqual(path.read_bytes(),raw)
            path.write_bytes(b'ABQDEFGH')
            with self.assertRaises(ValueError):service.preview_recipe(path,recipe)

    def test_unknown_code_paths_overlap_and_oversize_refuse(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';raw=b'ABCDEFGH';path.write_bytes(raw)
            for mutation in ({'kind':'shell','command':'anything'},{'kind':'bytes','offset':2,'before':'43','after':'58','path':'C:/secret'}):
                recipe=self.recipe(raw);recipe['operations']=[mutation]
                with self.assertRaises(ValueError):service.preview_recipe(path,recipe)
            recipe=self.recipe(raw);recipe['operations']*=2
            with self.assertRaisesRegex(ValueError,'overlap'):service.preview_recipe(path,recipe)
            recipe=self.recipe(raw);recipe['name']='x'*300000
            with self.assertRaises(ValueError):service.validate_recipe(recipe)

    def test_declared_numeric_and_pointerless_text_operations(self):
        service=self.service()
        with tempfile.TemporaryDirectory() as folder:
            raw=b'HELLO\0\xff\xff\x01\x02';path=Path(folder)/'source';path.write_bytes(raw)
            recipe=self.recipe(raw);recipe['operations']=[{'kind':'text','config':{'system_id':'gb','offset':0,'capacity':8,'count':1},'changes':[{'record_id':'line-0','segment':0,'before':'HELLO','after':'HI'}]},
                {'kind':'table','definition':{'schema_version':1,'name':'Stats','offset':8,'count':2,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]},'changes':[{'row':1,'field':'Value','before':2,'after':9}]}]
            result=service.preview_recipe(path,recipe);output=bytearray(raw)
            for edit in result['edits']:output[edit['offset']:edit['offset']+len(bytes.fromhex(edit['after']))]=bytes.fromhex(edit['after'])
            self.assertEqual(bytes(output),b'HI\0\xff\xff\xff\xff\xff\x01\x09')

    def test_api_saved_plan_recipe_and_definition_roundtrip(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'source';raw=bytearray(1024);raw[:8]=b'HELLO\0\xff\xff';raw[0x100:0x110]=b'SEGA MEGA DRIVE ';raw[0x1a4:0x1a8]=(1023).to_bytes(4,'big');raw=bytes(raw);path.write_bytes(raw);api=WorkbenchAPI(root/'workspace');self.addCleanup(api.close)
            project=api.dispatch('project.create',{'name':'Recipes'});source=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(path),'system':None});p={'project_id':project['project_id'],'artifact_id':source['artifact_id']}
            plan=api.dispatch('bytes.plan',{**p,'edits':[{'offset':0,'before':'48','after':'4a'}]})
            saved=api.dispatch('recipes.from_plan',{**p,'plan_id':plan['plan_id'],'name':'My edit'});self.assertTrue(saved['ok'],saved)
            a=api.dispatch('recipes.preview',{**p,'recipe':saved['recipe']});b=api.dispatch('recipes.preview',{**p,'recipe':saved['recipe']});self.assertEqual(a['plan_id'],b['plan_id'])
            built=api.dispatch('build.apply',{'project_id':p['project_id'],'plan_id':a['plan_id']});self.assertEqual(Path(built['path']).read_bytes(),b'J'+raw[1:])
            declared=api.dispatch('resources.declare_script',{**p,'config':{'system_id':'gb','offset':0,'capacity':8,'count':1}});self.assertTrue(declared['ok'],declared)
            exported=api.dispatch('definitions.export',{**p,'kind':'script'});file,_=api.download(p['project_id'],exported['export']['export_id'])
            import json
            document=json.loads(file.read_bytes());self.assertNotIn('path',document['source']);self.assertTrue(api.dispatch('definitions.import',{**p,'document':document})['ok'])
            with self.assertRaises(ValueError):self.service().import_definition(path,source['sha256'],{**document,'command':'ignored?'})

    def test_cancel_during_recipe_stops_operations_before_plan_or_export(self):
        from unittest.mock import patch
        from romancer.workbench_api import WorkbenchAPI
        from romancer.data_tables import table_edits
        from romancer.boot_fixtures import make_boot_fixture
        for system in ('gb','genesis'):
            with self.subTest(system=system):
                folder=self.enterContext(tempfile.TemporaryDirectory())
                root=Path(folder);raw=make_boot_fixture(system)['data'];path=root/'original';path.write_bytes(raw);api=WorkbenchAPI(root/'workspace');self.addCleanup(api.close)
                project=api.dispatch('project.create',{'name':'Cancel recipe'});source=api.dispatch('source.import',{'project_id':project['project_id'],'path':str(path),'system':None});p={'project_id':project['project_id'],'artifact_id':source['artifact_id']};recipe=self.recipe(raw);recipe['operations']=[]
                for index in range(128):recipe['operations'].append({'kind':'table','definition':{'schema_version':1,'name':'Values','offset':index,'count':1,'stride':1,'fields':[{'name':'Value','offset':0,'type':'u8','endian':'little','pointer_base':None}]},'changes':[{'row':0,'field':'Value','before':raw[index],'after':(raw[index]+1)%256}]})
                for operation in ('recipes.preview','recipes.export'):
                    calls=[]
                    def edit(*args):
                        result=table_edits(*args);calls.append(1);return result
                    with patch('romancer.data_tables.table_edits',side_effect=edit):result=api.dispatch(operation,{**p,'recipe':recipe},cancelled=lambda:bool(calls))
                    self.assertEqual(result['status'],'CANCELLED',result);self.assertEqual(len(calls),1)
                    self.assertFalse(list(Path(project['path']).joinpath('plans').glob('*.json')));self.assertFalse(api.exports(Path(project['path'])))

if __name__=='__main__':unittest.main()
