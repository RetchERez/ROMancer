import {selectionTicket,selectionCurrent} from './project_flow.js';
import {chooseArtifact} from './workbench_usability.js';

export async function setArtifactSelection(ctx,id,hooks,options={}){
 const {state}=ctx,project=state.project?.project_id,ticket=selectionTicket(state),navigation=state.navigationRevision;
 const current=()=>selectionCurrent(state,ticket)&&state.project?.project_id===project;
 hooks.rememberLocation();hooks.stopPlayback(state);state.animationPlaying=false;
 await hooks.flushDrafts();if(!current())return false;
 if(state.runtime){
  await ctx.api.call('runtime.close',{project_id:project});if(!current())return false;
  state.runtime=null;state.frame=null;state.snapshot=null;
 }
 await hooks.flushDrafts();if(!current())return false;
 hooks.clearDraftCache();state.artifact=chooseArtifact(state.project,id);
 hooks.writePreference('romancer-artifact:'+project,state.artifact?.artifact_id||'');
 state.profileFamily=null;state.profileLoadedFamily=null;state.scriptPage=0;state.assetPage=0;state.catalogPage=0;state.catalogQuery='';state.pending=null;
 if(options.restore!==false&&state.navigationRevision===navigation)hooks.resumeLocation();await ctx.render();return current();
}
