import assert from 'node:assert/strict';
import {createdBuild,playtestCreatedBuild} from '../romancer/ui/build_handoff.js';
const source={artifact_id:'a',sha256:'source'},build={artifact_id:'b',sha256:'target',source_id:'a',name:'My build'};
const state={project:{project_id:'p',sources:[source],builds:[build]},artifact:source,results:{'structured.apply':build}};
assert.equal(createdBuild(state),build);
state.results['structured.apply']={...build,sha256:'wrong'};assert.equal(createdBuild(state),null);
state.results['structured.apply']=build;state.artifact=build;assert.equal(createdBuild(state),null);
state.artifact=source;state.project.builds.push({...build,artifact_id:'c',sha256:'later'});state.results['build.apply']=state.project.builds[1];assert.equal(createdBuild(state).artifact_id,'c');
let page=null;const ctx={state,setArtifact:async id=>{state.artifact=state.project.builds.find(x=>x.artifact_id===id);state.selectionRevision=1;},navigate:async id=>{page=id;}};
await playtestCreatedBuild(ctx,'c');assert.equal(page,'playtest');assert.equal(state.artifact.artifact_id,'c');
state.artifact=source;page=null;ctx.setArtifact=async()=>{state.project={project_id:'other',sources:[],builds:[]};state.artifact=null;};
await assert.rejects(playtestCreatedBuild(ctx,'c'),/selection|selected|changed/i);assert.equal(page,null);
console.log('Created builds link to Playtest with recorded identity and selection guards.');

state.project={project_id:'p',sources:[source],builds:[build]};state.artifact=source;state.results={'structured.apply':build};page=null;ctx.setArtifact=async()=>{state.artifact=build;return false;};await assert.rejects(playtestCreatedBuild(ctx,'b'),/selection changed/);assert.equal(page,null,'a cancelled switch cannot navigate even if a newer selection chose the same build');
