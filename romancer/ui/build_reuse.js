// Reuse only the recorded output of this exact plan and input. The caller must
// reopen its source-bound definition through the service before selecting it.
export async function applyReviewedBuild(ctx,pending){
 const project=await ctx.api.call('project.open',ctx.projectParams());
 const existing=project.builds.find(b=>b.plan_id===pending.plan_id&&b.source_id===pending.artifact_id);
 return existing||ctx.run('build.apply',{...ctx.projectParams(),plan_id:pending.plan_id},{render:false});
}
