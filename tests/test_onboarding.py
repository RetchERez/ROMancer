import hashlib
from pathlib import Path
import tempfile
import unittest
from romancer.workbench_api import WorkbenchAPI


class OnboardingTests(unittest.TestCase):
    def test_short_basic_and_advanced_catalogue_and_durable_suppression(self):
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                value=api.dispatch('tutorial.get',{});self.assertTrue(value['ok'],value)
                self.assertTrue(value['prompt']);self.assertEqual(len(value['lessons']),4)
                self.assertEqual([x['section'] for x in value['lessons']],['Basic','Basic','Advanced','Advanced'])
                for lesson in value['lessons']:
                    self.assertIn(len(lesson['steps']),(3,4))
                    self.assertTrue(all(len(step['body'])<=160 for step in lesson['steps']))
                self.assertTrue(api.dispatch('tutorial.preferences',{'never_ask_again':True})['ok'])
            finally:api.close()
            api=WorkbenchAPI(Path(folder))
            try:self.assertFalse(api.dispatch('tutorial.get',{})['prompt'])
            finally:api.close()

    def test_only_completed_lessons_earn_checks_and_skipped_replay_keeps_earned_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                lessons=api.dispatch('tutorial.get',{});self.assertTrue(lessons['ok'],lessons)
                one,two=[x['id'] for x in lessons['lessons'][:2]]
                api.dispatch('tutorial.progress',{'lesson_id':one,'outcome':'completed'})
                api.dispatch('tutorial.progress',{'lesson_id':two,'outcome':'skipped'})
                api.dispatch('tutorial.progress',{'lesson_id':one,'outcome':'skipped'})
                value=api.dispatch('tutorial.get',{})
                self.assertEqual(value['progress'][one],'completed');self.assertEqual(value['progress'][two],'skipped')
                self.assertFalse(value['prompt'])
                for params in [{'lesson_id':'../outside','outcome':'completed'},{'lesson_id':one,'outcome':'PASS'}]:
                    self.assertFalse(api.dispatch('tutorial.progress',params)['ok'])
                self.assertFalse(api.dispatch('tutorial.preferences',{'never_ask_again':'yes'})['ok'])
            finally:api.close()

    def test_practice_is_explicit_reusable_and_preserves_user_source(self):
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                original=api.dispatch('project.demo_system',{'system_id':'gb'});source=Path(original['sources'][0]['path']);before=hashlib.sha256(source.read_bytes()).hexdigest()
                api.dispatch('tutorial.get',{});self.assertEqual(len(list(api.projects.iterdir())),1)
                one=api.dispatch('tutorial.practice',{});self.assertTrue(one['ok'],one)
                two=api.dispatch('tutorial.practice',{});self.assertEqual(one['project_id'],two['project_id'])
                self.assertEqual(one['name'],'Tutorial practice');self.assertEqual(one['demo_system'],'nes')
                self.assertEqual(len(list(api.projects.iterdir())),2);self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
            finally:api.close()

    def test_cancelled_practice_and_invalid_preferences_publish_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            api=WorkbenchAPI(Path(folder))
            try:
                self.assertEqual(api.dispatch('tutorial.practice',{},cancelled=lambda:True)['status'],'CANCELLED')
                self.assertFalse(api.dispatch('tutorial.preferences',{'never_ask_again':1})['ok'])
                self.assertFalse((Path(folder)/'tutorial.json').exists());self.assertEqual(list(api.projects.iterdir()),[])
            finally:api.close()
