import importlib
from pathlib import Path
import tempfile
import threading
import time
import unittest


class JobTests(unittest.TestCase):
    def test_completed_payloads_are_available_without_accumulating_in_memory(self):
        import gc,tracemalloc
        from romancer.workbench_jobs import JobManager
        with tempfile.TemporaryDirectory() as temp:
            manager=JobManager(Path(temp),lambda op,p,c:{'ok':True,'payload':str(p['index'])+'X'*131072},{'large'})
            tracemalloc.start()
            try:
                before=tracemalloc.get_traced_memory()[0];ids=[]
                for index in range(24):
                    submitted=manager.submit('large',{'index':index});ids.append(submitted['job_id']);deadline=time.monotonic()+5
                    while manager.get(ids[-1])['status'] not in ('COMPLETED','FAILED') and time.monotonic()<deadline:time.sleep(.005)
                    self.assertEqual(manager.get(ids[-1])['status'],'COMPLETED')
                gc.collect();retained=tracemalloc.get_traced_memory()[0]-before
                self.assertLess(retained,1024*1024,'Completed capture/scan payloads must be read from disk, not retained for every job.')
                self.assertEqual(manager.get(ids[0])['result']['payload'],'0'+'X'*131072)
                self.assertEqual(manager.get(ids[-1])['result']['payload'],'23'+'X'*131072)
            finally:manager.close();tracemalloc.stop()

    def test_retention_archives_terminal_jobs_without_blocking_workspace(self):
        from romancer.workbench_jobs import JobManager,write_json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'jobs').mkdir()
            for index in range(512):
                record={'job_id':f'{index:032x}','operation':'echo','status':'COMPLETED','created_at':index,
                        'message':'Completed','result':{'ok':True,'value':index}}
                write_json(root/'jobs'/(record['job_id']+'.json'),record)
            manager=JobManager(root,lambda op,p,c:{'ok':True,'value':999},{'echo'})
            try:
                job=manager.submit('echo',{});deadline=time.monotonic()+3
                while manager.get(job['job_id'])['status'] in ('RUNNING','QUEUED') and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(manager.get(job['job_id'])['status'],'COMPLETED')
                self.assertEqual(manager.get('0'*32)['result']['value'],0)
                self.assertLessEqual(len(manager.records),512)
            finally:manager.close()

    def test_late_cancel_does_not_relabel_completed_publication(self):
        from romancer.workbench_jobs import JobManager
        with tempfile.TemporaryDirectory() as temp:
            started=threading.Event()
            def handler(op,p,c):
                started.set()
                while not c():time.sleep(.01)
                return {'ok':True,'status':'VERIFIED','written':True}
            manager=JobManager(Path(temp),handler,{'publish'})
            try:
                job=manager.submit('publish',{});self.assertTrue(started.wait(2));manager.cancel(job['job_id'])
                deadline=time.monotonic()+3
                while manager.get(job['job_id'])['status'] in ('RUNNING','QUEUED') and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(manager.get(job['job_id'])['status'],'COMPLETED')
            finally:manager.close()
    def test_cancel_running_persist_restart_unknown_and_result(self):
        try:m=importlib.import_module('romancer.workbench_jobs')
        except ModuleNotFoundError:m=None
        self.assertIsNotNone(m,'owned job manager is missing')
        with tempfile.TemporaryDirectory() as temp:
            started=threading.Event()
            def handler(operation,parameters,cancelled):
                started.set()
                if operation=='wait':
                    while not cancelled():time.sleep(.01)
                    return {'ok':False,'status':'CANCELLED','written':False}
                return {'ok':True,'status':'DONE','value':parameters['value']}
            manager=m.JobManager(Path(temp),handler,{'wait','echo'})
            job=manager.submit('wait',{});self.assertTrue(started.wait(2));manager.cancel(job['job_id'])
            deadline=time.monotonic()+3
            while manager.get(job['job_id'])['status'] not in ('CANCELLED','FAILED','COMPLETED') and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(manager.get(job['job_id'])['status'],'CANCELLED')
            with self.assertRaises(ValueError):manager.submit('shell',{'command':'anything'})
            manager.close();other=m.JobManager(Path(temp),handler,{'wait','echo'})
            self.assertEqual(other.get(job['job_id'])['status'],'CANCELLED');other.close()
