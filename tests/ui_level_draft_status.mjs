import assert from 'node:assert/strict';
import {hasStagedChanges,guardClose} from '../romancer/ui/workspace_status.js';
const state={project:{project_id:'p'},artifact:{artifact_id:'a'},drafts:{'p:a:levels:level-changes':JSON.stringify({document_id:'B',changes:[]}), 'p:a:levels:level-layout-draft-A':JSON.stringify({document_id:'A',changes:[{kind:'terrain',room_id:'r',index:0,value:1}]})}};
assert.equal(hasStagedChanges(state),true);let prevented=false;guardClose({preventDefault(){prevented=true;}},{snapshot:()=>({unsafe:false})},state);assert(prevented);
state.artifact={artifact_id:'other'};assert.equal(hasStagedChanges(state),false);state.artifact={artifact_id:'a'};state.drafts['p:a:levels:level-layout-draft-A']=JSON.stringify({document_id:'A',changes:[]});assert.equal(hasStagedChanges(state),false);
console.log('Unbuilt per-layout drafts retain status and close protection, stay source-scoped and clear after build.');
