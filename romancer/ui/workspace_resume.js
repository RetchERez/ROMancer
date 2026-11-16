import {selectionKey} from './tool_inputs.js';
import {writePreference} from './preferences.js';
export function seedWorkspaceLocation(saved){if(!saved)return;if(saved.page==='levels')saved={...saved,page:'overview',scroll:0};if(saved.page==='tutorials')saved={...saved,page:'help'};writePreference('romancer-project',saved.project_id);writePreference('romancer-artifact:'+saved.project_id,saved.artifact_id);writePreference('romancer-location:'+saved.project_id+':'+saved.artifact_id,JSON.stringify(saved));}
export class WorkspaceLocationWriter{
 constructor(api,failed=()=>{},saved=()=>{}){this.api=api;this.failed=failed;this.saved=saved;this.pending=null;this.hasPending=false;this.promise=null;}
 enqueue(location){this.pending=location;this.hasPending=true;if(!this.promise)this.promise=this.drain().finally(()=>{this.promise=null;if(this.hasPending)this.enqueue(this.pending);});return this.promise;}
 async drain(){while(this.hasPending){const location=this.pending;this.hasPending=false;try{await this.api.call('settings.workspace.save',{location});this.saved(location);}catch(error){this.failed(error);}}}
}
const pages=new Set(['overview','gameview','resources','scripts','assets','tables','sound','playtest','release','automation','help','settings','debug','routes','regression']);
const integer=(value,max)=>Number.isSafeInteger(value)&&value>=0&&value<=max;
export const locationKey=state=>'romancer-location:'+state.project?.project_id+':'+state.artifact?.artifact_id;
export function locationSnapshot(state,scroll=0){
 const a=state.artifact;if(!state.project||!a||!pages.has(state.page))return null;
 const data=state.results?.['resource.inspect'],bound=data?.artifact_id===a.artifact_id&&data.sha256===a.sha256;
 const offset=bound?data.offset:0,selected=state.hexDraft?.scope===selectionKey(state)?state.hexDraft.selected:offset;
 return {version:1,project_id:state.project.project_id,artifact_id:a.artifact_id,sha256:a.sha256,page:state.page,
  offset:integer(offset,Math.max(0,a.size-1))?offset:0,selected:integer(selected,Math.max(0,a.size-1))?selected:offset,
  scroll:Number.isFinite(scroll)?Math.max(0,Math.min(1e7,scroll)):0,
  assetPage:integer(state.assetPage,100000)?state.assetPage:0,scriptPage:integer(state.scriptPage,100000)?state.scriptPage:0,
  catalogPage:integer(state.catalogPage,100000)?state.catalogPage:0,catalogQuery:typeof state.catalogQuery==='string'?state.catalogQuery.slice(0,256):''};
}
export function restoreLocation(state,saved){
 if(saved?.page==='levels')saved={...saved,page:'overview',scroll:0};
 const a=state.artifact;
 if(!a||!saved||saved.version!==1||saved.project_id!==state.project?.project_id||saved.artifact_id!==a.artifact_id||saved.sha256!==a.sha256||!pages.has(saved.page))return false;
 if(!integer(saved.offset,Math.max(0,a.size-1))||!integer(saved.selected,Math.max(0,a.size-1))||!Number.isFinite(saved.scroll)||saved.scroll<0||saved.scroll>1e7)return false;
 if(!['assetPage','scriptPage','catalogPage'].every(k=>integer(saved[k],100000))||typeof saved.catalogQuery!=='string'||saved.catalogQuery.length>256)return false;
 Object.assign(state,{page:saved.page,resourceJump:saved.offset,resumeHexSelection:saved.selected,resumeScroll:saved.scroll,assetPage:saved.assetPage,scriptPage:saved.scriptPage,catalogPage:saved.catalogPage,catalogQuery:saved.catalogQuery});
 state.resumeIdentity=saved.project_id+':'+a.artifact_id+':'+a.sha256;
 return true;
}
