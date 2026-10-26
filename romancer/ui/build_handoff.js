import {selectionKey} from './tool_inputs.js';

// Offer only a build produced in this session and recorded for this input.
export function createdBuild(state){
 if(!state.project||!state.artifact)return null;
 const results=['structured.apply','build.apply','patches.apply'].map(key=>state.results?.[key]);
 return [...state.project.builds].reverse().find(row=>row.source_id===state.artifact.artifact_id&&results.some(result=>result?.artifact_id===row.artifact_id&&result.sha256===row.sha256))||null;
}
export async function playtestCreatedBuild(ctx,id){
 const build=createdBuild(ctx.state),project=ctx.state.project?.project_id;
 if(!build||build.artifact_id!==id)throw Error('The selected build changed. Choose it again from Build history.');
 const target=build.sha256,navigation=ctx.state.navigationRevision;
 const selected=await ctx.setArtifact(id);
 if(selected===false)throw Error('The selection changed. Choose your build before playtesting.');
 if(ctx.state.project?.project_id!==project||ctx.state.artifact?.artifact_id!==id||ctx.state.artifact.sha256!==target)throw Error('The selection changed. Choose your build before playtesting.');
 if(ctx.state.navigationRevision!==navigation)return;
 const scope=selectionKey(ctx.state);
 await ctx.navigate('playtest');
 if(selectionKey(ctx.state)!==scope)throw Error('The selection changed while opening Playtest.');
}
