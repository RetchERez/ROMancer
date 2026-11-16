"""Persistent investigations captured by the owned native runtime, never imports."""
from .asset_schema import label,number
from .observation_series import analyze_series,validate_observations
from .workbench_evidence import load_evidence,store_evidence
from .release_scope import require_supported


class InvestigationTools:
    def __init__(self,api):self.api=api

    def routes(self):
        return {'investigations.start':('project_id artifact_id title region offset length value',self.start),
            'investigations.capture':('project_id artifact_id investigation_id label value relation delta',self.capture),
            'investigations.get':('project_id artifact_id investigation_id',self.get),
            'investigations.probe':('project_id artifact_id investigation_id candidate_id',self.probe)}

    def _load(self,p):
        project,row,_=self.api.source(p);require_supported(row)
        record=load_evidence(project,p['investigation_id'],'runtime');report=record['report']
        if (report.get('kind')!='investigation-series-v1' or report.get('source_sha256')!=row['sha256']
                or report.get('artifact_id')!=row['artifact_id']):
            raise ValueError('investigation belongs to another selected source')
        validate_observations(report['observations'],1);label(report['title'],120)
        return project,row,record

    def _public(self,record,cancelled):
        report=record['report'];observations=report['observations']
        validate_observations(observations,1)
        analysis=analyze_series(observations,cancelled=cancelled) if len(observations)>1 else {
            'status':'NEEDS_MORE','candidates':[],'total':0,'truncated':False,'observation_count':1,
            'unchanged_controls':0,'next_experiment':'Play until the target changes, pause, and capture another observation.'}
        return {'ok':True,**analysis,'source_sha256':report['source_sha256'],'artifact_id':report['artifact_id'],
            'investigation_id':record['evidence_id'],'title':report['title'],
            'runtime_trusted':record.get('runtime_trusted',True),
            'history':[{'label':o['label'],'value':o['value'],'relation':o['relation'],'delta':o['delta'],
                'sequence':o['snapshot']['sequence'],'frame_index':o['snapshot'].get('frame_index'),
                'data_sha256':o['snapshot']['data_sha256']} for o in observations],
            'rom_location_known':False,'causation_proven':False,'write_authorized':False,'memory_written':False}

    def start(self,p,c):
        project,row,_=self.api.source(p);require_supported(row);label(p['title'],120)
        number(p['region'],0,3);number(p['offset'],0,256*1024**2);number(p['length'],1,4096)
        if p['value'] is not None:number(p['value'],-2**31,2**32-1)
        with self.api.runtime.lock:
            packet=self.api.studio.observe(p,c,p['region'],p['offset'],p['length'])
            observations=[{'snapshot':packet,'label':'Before','value':p['value'],'relation':'initial','delta':None}]
            validate_observations(observations,1)
            if c():raise KeyboardInterrupt
            record=store_evidence(project,'runtime',{'kind':'investigation-series-v1','artifact_id':row['artifact_id'],
                'source_sha256':row['sha256'],'title':p['title'],'observations':observations})
        return self._public(record,c)

    def capture(self,p,c):
        project,row,record=self._load(p)
        if not record['runtime_trusted']:raise ValueError('historical investigations are read-only; start a fresh native investigation')
        report=record['report'];observations=report['observations']
        if len(observations)>=32:raise ValueError('investigation reached 32 observations; start a new focused investigation')
        label(p['label'],120);first=observations[0]['snapshot']
        with self.api.runtime.lock:
            packet=self.api.studio.observe(p,c,first['region'],first['offset'],first['length'])
            observations=observations+[{'snapshot':packet,'label':p['label'],'value':p['value'],
                'relation':p['relation'],'delta':p['delta']}]
            validate_observations(observations)
            analyze_series(observations,cancelled=c)
            if c():raise KeyboardInterrupt
            replay=self._playtest_replay(project,row['system_id'],observations[-2]['snapshot'],packet)
            record=store_evidence(project,'runtime',{**report,'parent_evidence_id':record['evidence_id'],
                'observations':observations,'playtest_replay':replay})
        return self._public(record,c)

    def _playtest_replay(self,project,system,previous,current):
        from .debugger_protocol import BUTTONS
        start,end=previous.get('frame_index'),current.get('frame_index')
        if type(start) is not int or type(end) is not int or not 0<=start<end<=3600:
            return None
        try:
            replay=self.api.runtime.replay_snapshot(project,{'index':end,'game_sha256':current['game_sha256'],
                'core_sha256':current['core_sha256']})
        except (ValueError,KeyError):
            return None
        steps=replay.get('steps',[])
        if replay['status']!='READY' or replay['frames']!=end or not 1<=len(steps)<=64 or any(s['port']!=0 for s in steps):
            return None
        if any(device!=1 for device in replay.get('context',{}).get('controller_devices',{}).values()):
            return None
        # The debugger uses console button names; the frontend records RetroPad inputs.
        names={'genesis':{'a':'b','b':'a','r':'c'},'sms':{'a':'one','b':'two','start':'pause'}}.get(system,{})
        steps=[{**step,'buttons':[names.get(key,key) for key in step['buttons']]} for step in steps]
        if any(set(step['buttons'])-BUTTONS[system] for step in steps):
            return None
        return {'steps':steps,'frames':end,'start_frame':start}

    def get(self,p,c):
        _,_,record=self._load(p);return self._public(record,c)

    def probe(self,p,c):
        from .core_memory_layout import memory_probe
        _,row,record=self._load(p)
        if not record['runtime_trusted']:raise ValueError('Historical investigations cannot supply a fresh native probe; capture a new investigation.')
        report=record['report'];observations=report['observations']
        if len(observations)<2:raise ValueError('Capture a controlled change before investigating accesses.')
        analysis=analyze_series(observations,cancelled=c)
        candidate=next((r for r in analysis['candidates'] if r['candidate_id']==p['candidate_id']),None)
        if candidate is None:raise ValueError('Candidate is not a current authenticated investigation hypothesis.')
        proposed=memory_probe(row['system_id'],observations[0]['snapshot'],candidate['offset'],candidate['width'])
        return {**proposed,'source_sha256':row['sha256'],'artifact_id':row['artifact_id'],
            'investigation_id':record['evidence_id'],'candidate':candidate,'causation_proven':False,
            'playtest_replay':report.get('playtest_replay'),
            'replay_scope':'A new debugger replay starts from power on. It does not resume the Playtest worker or convert its save state.'}
