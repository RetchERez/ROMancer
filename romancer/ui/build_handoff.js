
// Offer only a build produced in this session and recorded for this input.
export function createdBuild(state){
 if(!state.project||!state.artifact)return null;
 const results=['structured.apply','build.apply','patches.apply'].map(key=>state.results?.[key]);
 return [...state.project.builds].reverse().find(row=>row.source_id===state.artifact.artifact_id&&results.some(result=>result?.artifact_id===row.artifact_id&&result.sha256===row.sha256))||null;
}
export function originalForBuild(project,target){
 const sources=new Map((project?.sources||[]).map(r=>[r.artifact_id,r])),builds=new Map((project?.builds||[]).map(r=>[r.artifact_id,r])),seen=new Set();
 let row=builds.get(target?.artifact_id)||sources.get(target?.artifact_id);if(!row||row.sha256!==target.sha256)return null;
 for(let i=0;row&&i<128;i++){
  if(seen.has(row.artifact_id))return null;seen.add(row.artifact_id);
  if(sources.has(row.artifact_id))return sources.get(row.artifact_id);
  row=builds.get(row.source_id)||sources.get(row.source_id);
 }
 return null;
}
export function continuedBuild(state){
 if(!state.project||!state.artifact)return null;
 const rows=[...(state.project.sources||[]),...(state.project.builds||[])],selected=rows.find(r=>r.artifact_id===state.artifact.artifact_id&&r.sha256===state.artifact.sha256);
 if(!selected)return null;
 const candidate=createdBuild(state)||(state.project.builds||[]).find(r=>r.artifact_id===selected.artifact_id)||[...(state.project.builds||[])].reverse().find(r=>r.source_id===selected.artifact_id);
 return candidate&&originalForBuild(state.project,candidate)?candidate:null;
}
async function openBuild(ctx,id,page){
 const build=continuedBuild(ctx.state),project=ctx.state.project?.project_id,navigation=ctx.state.navigationRevision;
 if(!build||build.artifact_id!==id)throw Error('The selected build changed. Choose it again from Build history.');
 if(ctx.state.artifact?.artifact_id!==id){const selected=await ctx.setArtifact(id,{restore:false});if(selected===false)throw Error('The selection changed. Choose your build again.');}
 if(ctx.state.project?.project_id!==project||ctx.state.artifact?.artifact_id!==id||ctx.state.artifact.sha256!==build.sha256)throw Error('The selection changed. Choose your build again.');
 if(ctx.state.navigationRevision!==navigation)return false;
 if(page==='release'){
  const original=originalForBuild(ctx.state.project,build);
  if(!original)throw Error('The original for this build is unavailable. Open Build history.');
  ctx.state.releaseHandoff={project_id:project,artifact_id:id,sha256:build.sha256,source_id:original.artifact_id,source_sha256:original.sha256};
 }
 return ctx.navigate(page);
}
export const checkCreatedBuild=(ctx,id)=>openBuild(ctx,id,'gameview');
export const exportCreatedBuild=(ctx,id)=>openBuild(ctx,id,'release');
export async function editBuildInput(ctx,id){
 const build=continuedBuild(ctx.state),project=ctx.state.project?.project_id,navigation=ctx.state.navigationRevision;
 if(!build||build.artifact_id!==id)throw Error('The selected build changed. Choose it again from Build history.');
 const input=[...(ctx.state.project.sources||[]),...(ctx.state.project.builds||[])].find(r=>r.artifact_id===build.source_id);
 if(!input)throw Error('This build input is unavailable. Open Build history.');
 const selected=await ctx.setArtifact(input.artifact_id);
 if(selected===false||ctx.state.project?.project_id!==project||ctx.state.artifact?.artifact_id!==input.artifact_id||ctx.state.artifact.sha256!==input.sha256)throw Error('The selection changed while opening the build input.');
 if(ctx.state.navigationRevision!==navigation)return false;
 if(!['assets','scripts','tables','levels','sound','resources','debug','gameview'].includes(ctx.state.page))return ctx.navigate('overview');
}
export async function playtestCreatedBuild(ctx,id){
 return openBuild(ctx,id,'playtest');
}
