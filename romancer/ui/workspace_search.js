const aliases={assets:'palette color colour sprite tiles graphics font',resources:'hex bytes offsets compare files checksums crc rom',scripts:'text dialogue translation encoding layout',tables:'numbers stats balance values table',levels:'map rooms terrain objects level',sound:'music sound audio samples',playtest:'play emulator controller save state load state',debug:'investigate find value memory watch trace',release:'export patch bps ips download',settings:'theme light dark size zoom preferences',help:'guide tutorial help shortcuts'};
export function workspaceMatches(query,names,project){
 const words=String(query).toLowerCase().trim().split(/\s+/).filter(Boolean),matches=[];
 for(const [page,label] of Object.entries(names))if(words.every(w=>(label+' '+(aliases[page]||'')).toLowerCase().includes(w)))matches.push({page,label,kind:'tool'});
 for(const row of [...project?.sources||[],...project?.builds||[]])if(words.every(w=>(row.name+' '+row.kind).toLowerCase().includes(w)))matches.push({artifact_id:row.artifact_id,sha256:row.sha256,project_id:project.project_id,label:row.name,kind:row.kind});
 return matches.slice(0,32);
}
export async function openSearchFile(ctx,project,id,sha){
 const navigation=ctx.state.navigationRevision;
 const row=[...ctx.state.project?.sources||[],...ctx.state.project?.builds||[]].find(r=>r.artifact_id===id&&r.sha256===sha);
 if(ctx.state.project?.project_id!==project||!row)throw Error('This file changed. Search again.');
 if(await ctx.setArtifact(id,{restore:false})===false)return;
 if(ctx.state.navigationRevision===navigation&&ctx.state.project?.project_id===project&&ctx.state.artifact?.artifact_id===id&&ctx.state.artifact.sha256===sha)await ctx.navigate('resources');
}
