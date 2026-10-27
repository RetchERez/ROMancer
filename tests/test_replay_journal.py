import unittest
from romancer.replay_journal import ReplayJournal,execution_context

class ReplayJournalTests(unittest.TestCase):
    def test_acknowledged_steps_coalesce_without_claiming_extra_frames(self):
        j=ReplayJournal();j.acknowledge('advance',{'frames':12,'buttons':['a'],'port':0},{'frame_index':12})
        j.acknowledge('advance',{'frames':12,'buttons':['a'],'port':0},{'frame_index':24})
        r=j.snapshot(24);self.assertEqual(r['status'],'READY');self.assertEqual(r['steps'],[{'frames':24,'buttons':['a'],'port':0}])
        self.assertEqual(j.snapshot(25)['status'],'UNAVAILABLE')
        j.acknowledge('capture',{},{});self.assertEqual(j.snapshot(24)['status'],'READY')

    def test_state_reset_save_restore_and_budget_invalidate_without_truncating_into_authority(self):
        for operation in ('load_state','reset','import_game_save'):
            with self.subTest(operation=operation):
                j=ReplayJournal();j.acknowledge(operation,{},{});self.assertEqual(j.snapshot(0)['status'],'UNAVAILABLE')
        j=ReplayJournal(game_save=True);self.assertEqual(j.snapshot(0)['status'],'UNAVAILABLE')
        j=ReplayJournal()
        for n in range(61):j.acknowledge('advance',{'frames':600,'buttons':[],'port':0},{'frame_index':(n+1)*600})
        self.assertEqual(j.snapshot(36600)['status'],'UNAVAILABLE');self.assertEqual(j.steps,[])

    def test_execution_context_excludes_personal_paths_but_binds_options_and_firmware(self):
        a={'core':'C:/private/core.dll','expected_core_sha256':'a'*64,'core_options':{'mode':'one'},'controller_devices':{'0':1},'system_dir':'C:/private','system_files':[{'source':'C:/private/bios','relative':'bios.bin','expected_sha256':'b'*64,'size':42}]}
        c=execution_context(a);self.assertNotIn('private',str(c));b={**a,'core':'other','system_dir':'other'};self.assertEqual(c,execution_context(b))
        self.assertNotEqual(c,execution_context({**a,'core_options':{'mode':'two'}}))

if __name__=='__main__':unittest.main()
