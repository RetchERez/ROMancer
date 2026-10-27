"""Bounded acknowledged cold-start inputs, never a caller's claimed history."""
import copy
from .runtime_session import validate_steps


def execution_context(load):
    return {'core_sha256':load['expected_core_sha256'],'core_options':copy.deepcopy(load.get('core_options',{})),
            'controller_devices':copy.deepcopy(load.get('controller_devices',{})),
            'system_files':[{'relative':r['relative'],'sha256':r['expected_sha256']} for r in load.get('system_files',[])]}


class ReplayJournal:
    def __init__(self,*,game_save=False):
        self.steps=[];self.frames=0;self.reason='A battery-save load needs a fresh cold start for source verification.' if game_save else None

    def invalidate(self,reason):self.reason=reason;self.steps=[]

    def acknowledge(self,operation,parameters,result):
        if self.reason:return
        if operation in ('load_state','reset','import_game_save'):
            self.invalidate('State or reset changed the initial conditions. Close and load the game again to verify sources.');return
        if operation!='advance':return
        validate_steps([parameters]);step=copy.deepcopy(parameters);step['buttons']=sorted(step['buttons'])
        expected=self.frames+step['frames']
        if result.get('frame_index')!=expected:
            self.invalidate('The acknowledged frame count differs from the cold-start journal.');return
        self.frames=expected
        if self.steps and all(self.steps[-1][k]==step[k] for k in ('buttons','port')) and self.steps[-1]['frames']+step['frames']<=600:self.steps[-1]['frames']+=step['frames']
        else:self.steps.append(step)
        if self.frames>36000 or len(self.steps)>2048:self.invalidate('Replay exceeds 36,000 frames or 2048 input steps. Start a shorter fresh session.')

    def snapshot(self,frame):
        if self.reason or type(frame) is not int or frame!=self.frames:return {'status':'UNAVAILABLE','reason':self.reason or 'Captured frame differs from the acknowledged replay history.'}
        return {'status':'READY','version':1,'frames':self.frames,'steps':copy.deepcopy(self.steps)}
