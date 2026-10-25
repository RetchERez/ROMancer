"""Bounded owned background jobs with persisted terminal results and cancellation."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
import uuid
from .assets import checked_path
from .runtime_session import snapshot_json
from .script_schema import load_script_json
from .workbench_projects import identifier,write_json

TERMINAL={'COMPLETED','FAILED','CANCELLED','INTERRUPTED'}


class JobManager:
    def __init__(self,workspace,handler,operations):
        self.root=checked_path(Path(workspace)/'jobs');self.root.mkdir(parents=True,exist_ok=True)
        self.archive=checked_path(self.root/'archive');self.archive.mkdir(exist_ok=True)
        self.handler=handler;self.operations=set(operations);self.records={};self.events={};self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='romancer-job');self.closed=False
        for path in sorted(self.root.glob('*.json'))[-512:]:
            try:
                record=load_script_json(path,max_bytes=8*1024**2);identifier(record['job_id'])
                if record['status'] not in TERMINAL:
                    record.update(status='INTERRUPTED',message='Application closed before the job finished; inspect outputs before retrying.')
                    write_json(path,record)
                record['result']=None
                self.records[record['job_id']]=record
            except (ValueError,OSError,KeyError):continue

    def _save(self,record):write_json(self.root/(record['job_id']+'.json'),record)

    def submit(self,operation,parameters):
        if operation not in self.operations:raise ValueError('operation is not registered for background execution')
        parameters=snapshot_json(parameters)
        with self.lock:
            if self.closed:raise ValueError('job manager is closing')
            if sum(r['status'] not in TERMINAL for r in self.records.values())>=8:raise ValueError('job queue is full; wait or cancel an active job')
            while len(self.records)>=512:
                completed=[r for r in self.records.values() if r['status'] in TERMINAL]
                if not completed:raise ValueError('job history is busy; wait for an active job')
                old=min(completed,key=lambda r:r.get('finished_at',r.get('created_at',0)))
                previous=checked_path(self.root/(old['job_id']+'.json'));archived=checked_path(self.archive/previous.name)
                os.link(previous,archived);previous.unlink()
                self.records.pop(old['job_id']);self.events.pop(old['job_id'],None)
            job_id=uuid.uuid4().hex;event=threading.Event();self.events[job_id]=event
            record={'job_id':job_id,'operation':operation,'status':'QUEUED','created_at':time.time(),
                    'message':'Waiting for a worker','cancel_requested':False,'result':None}
            self.records[job_id]=record;self._save(record)
            self.pool.submit(self._run,job_id,parameters)
            return snapshot_json(record)

    def _run(self,job_id,parameters):
        with self.lock:
            record=self.records[job_id];event=self.events[job_id]
            if event.is_set():record.update(status='CANCELLED',message='Cancelled before execution');self._save(record);self.events.pop(job_id,None);return
            record.update(status='RUNNING',message='Running '+record['operation'],started_at=time.time());self._save(record)
        try:
            result=self.handler(record['operation'],parameters,event.is_set)
            # Persist result facts even when cancellation arrives during publication.
            status='CANCELLED' if result.get('status')=='CANCELLED' else ('COMPLETED' if result.get('ok') is True else ('CANCELLED' if event.is_set() else 'FAILED'))
        except (Exception,KeyboardInterrupt) as exc:
            status='CANCELLED' if isinstance(exc,KeyboardInterrupt) or event.is_set() else 'FAILED'
            result={'ok':False,'status':status,'error':str(exc)[:1024] or 'Operation cancelled'}
        with self.lock:
            record.update(status=status,result=result,finished_at=time.time(),message='Completed before cancellation took effect' if status=='COMPLETED' and event.is_set() else status.capitalize())
            try:
                self._save(record)
                record['result']=None
            except (ValueError,OSError):record.update(status='FAILED',result={'ok':False,'error':'Result could not be saved; inspect project outputs before retrying.'},message='Result could not be saved; inspect project outputs before retrying.')
            self.events.pop(job_id,None)

    def get(self,job_id):
        identifier(job_id)
        with self.lock:
            if job_id not in self.records:
                path=checked_path(self.archive/(job_id+'.json'))
                if not path.exists():raise ValueError('unknown job identifier')
                record=load_script_json(path,max_bytes=8*1024**2)
                if record.get('job_id')!=job_id or record.get('status') not in TERMINAL:raise ValueError('invalid archived job')
                return record
            # Results have an 8 MiB budget, larger than operation parameters.
            record=self.records[job_id]
            if record['status'] in TERMINAL and record.get('result') is None:
                saved=load_script_json(checked_path(self.root/(job_id+'.json')),max_bytes=8*1024**2)
                if saved.get('job_id')!=job_id or saved.get('status') not in TERMINAL:raise ValueError('invalid persisted job')
                return saved
            return json.loads(json.dumps(record))

    def list(self):
        with self.lock:return [{k:v for k,v in r.items() if k!='result'} for r in list(self.records.values())[-50:]][::-1]

    def cancel(self,job_id):
        identifier(job_id)
        with self.lock:
            record=self.records.get(job_id)
            if record is None:return self.get(job_id)
            if record['status'] not in TERMINAL:
                self.events[job_id].set();record.update(cancel_requested=True,message='Cancellation requested; waiting for cleanup');self._save(record)
            return self.get(job_id)

    def close(self):
        with self.lock:
            self.closed=True
            for event in self.events.values():event.set()
        self.pool.shutdown(wait=True,cancel_futures=False)
