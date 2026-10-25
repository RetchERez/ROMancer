import {selectionKey} from './tool_inputs.js';
export function chooseArtifact(project,id){const rows=project.sources.concat(project.builds);return rows.find(r=>r.artifact_id===id)||project.sources[0]||project.builds[0]||null;}
export function shouldSaveField(node){return !!node.id&&!node.closest('dialog')&&!['global-search','project-select','artifact-select'].includes(node.id)&&!['file','hidden','checkbox','radio'].includes(node.type);}
export const retainedScroll=(previous,next,scroll)=>previous===next?Math.max(0,scroll):0;
function detailsEntries(root){const counts=new Map();return [...root.querySelectorAll('details')].map(node=>{const summary=node.querySelector(':scope > summary')?.textContent.split(' ·')[0].trim()||'',index=counts.get(summary)||0;counts.set(summary,index+1);return [node.id||summary+':'+index,node];});}
export const rememberDetails=root=>root?new Map(detailsEntries(root).map(([key,node])=>[key,node.open])):new Map();
export function restoreDetails(root,saved){for(const [key,node] of detailsEntries(root))if(saved.has(key))node.open=saved.get(key);}
export async function runScoped(ctx,operation,parameters,options={},updateJob=()=>{}){
 const {state}=ctx,scope=selectionKey(state),current=()=>scope===selectionKey(state);
 const changed=()=>Error('Action finished for the previous selection. Open that project or file to review its result.');
 let result;
 try{result=await ctx.api.job(operation,parameters,updateJob);}catch(error){if(!current())throw changed();if(error.result)state.results[operation]=error.result;if(options.render!==false)await ctx.render();throw error;}
 if(!current())throw changed();if(options.refresh!==false)await ctx.refreshProject();if(!current())throw changed();
 state.results[operation]=result;if(options.render!==false)await ctx.render();return result;
}
