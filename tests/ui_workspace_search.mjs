import assert from 'node:assert/strict';
import {workspaceMatches,openSearchFile} from '../romancer/ui/workspace_search.js';
const names={assets:'Graphics & fonts',resources:'Resources',tables:'Data tables',playtest:'Playtest'},project={project_id:'p',sources:[{artifact_id:'a',name:'My ROM.nes',kind:'source',sha256:'a'}],builds:[{artifact_id:'b',name:'Sprite edit',kind:'build',sha256:'b'}]};
for(const [query,page] of [['palette','assets'],['sprite','assets'],['hex','resources'],['save state','playtest'],['stats','tables']])assert(workspaceMatches(query,names,project).some(row=>row.page===page));
assert(workspaceMatches('sprite edit',names,project).some(row=>row.artifact_id==='b'));assert.equal(workspaceMatches('does not exist',names,project).length,0);
let navigated=false;const state={project,artifact:project.sources[0]};const ctx={state,setArtifact:async()=>{state.artifact=project.builds[0];return true;},navigate:async()=>navigated=true};await openSearchFile(ctx,'p','b','b');assert(navigated);
navigated=false;state.artifact=project.sources[0];ctx.setArtifact=async()=>{state.project={project_id:'other'};return false;};await openSearchFile(ctx,'p','b','b');assert(!navigated);
console.log('Search aliases find tools and exact files without overriding newer selections.');
