import assert from 'node:assert/strict';
import fs from 'node:fs';
const path=new URL('../romancer/ui/data_relocation.js',import.meta.url);
assert.ok(fs.existsSync(path),'Declared relocation needs a guided advanced form.');
const {relocationControls}=await import(path);
const values={'reloc-source':'4096','reloc-length':'16','reloc-target':'6144','reloc-capacity':'64','reloc-fill':'255',
 'reloc-alignment':'1','reloc-bank':'16384','reloc-origin':'16','reloc-ref-offset-0':'513','reloc-ref-width-0':'2',
 'reloc-ref-endian-0':'little','reloc-ref-base-0':'32752','reloc-ref-delta-0':'0'};
globalThis.document={getElementById:id=>({value:values[id]??'',checked:true})};
function fixture(){
 const actions={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',system_id:'nes'},results:{}};
 const calls=[],ctx={state,use:r=>Object.assign(actions,r),draft:(k,d)=>d,setDraft(){},sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),
 projectParams:()=>({project_id:'p'}),render:async()=>{},notify(){},run:async(op,p)=>{calls.push([op,p]);return {ok:true,plan_id:'plan',source_sha256:'sha',artifact_id:'a',relocation:{payload_size:16,pointer_updates:[]}};}};
 return {ctx,state,actions,calls};
}
{
 const {ctx,state,actions,calls}=fixture();assert.match(await relocationControls(ctx),/reserved|references/i);
 await actions['reloc-review']();assert.equal(calls[0][1].spec.references_complete,true);
 assert.equal(calls[0][1].spec.references[0].base,32752);assert.equal(state.pending.kind,'relocation');
 values['reloc-target']='6208';await assert.rejects(actions['reloc-build'](),/changed|review/i);values['reloc-target']='6144';
 await actions['reloc-review']();await actions['reloc-build']();assert.equal(calls.at(-1)[0],'build.apply');
 assert.equal(state.pending,null);
}
{
 const {ctx,state,actions}=fixture();await relocationControls(ctx);let finish;ctx.run=()=>new Promise(resolve=>finish=resolve);
 const pending=actions['reloc-review']();state.selectionRevision=2;finish({ok:true,plan_id:'stale',source_sha256:'sha',artifact_id:'a'});await pending;
 assert.equal(state.pending,undefined,'A late relocation plan cannot attach to another selection.');
}
console.log('Declared relocation UI preserves reviewed form values, source scope and separate builds.');
