import assert from 'node:assert/strict';
import fs from 'node:fs';
const modulePath=new URL('../romancer/ui/investigation_series.js',import.meta.url);
assert.ok(fs.existsSync(modulePath),'The guided universal investigation UI is missing.');
const {investigationSeries,seriesNumber}=await import(modulePath);
const {releaseProjectResources}=await import('../romancer/ui/project_flow.js');
assert.equal(seriesNumber(''),null);assert.equal(seriesNumber('0x10'),16);assert.equal(seriesNumber('-3'),-3);
assert.throws(()=>seriesNumber('1.5'));assert.throws(()=>seriesNumber('Infinity'));
const result={ok:true,source_sha256:'sha',artifact_id:'a',investigation_id:'e',title:'A <number>',status:'ANALYZED',
 runtime_trusted:true,total:1,truncated:false,observation_count:3,unchanged_controls:1,
 history:[{label:'Before',value:1000,relation:'initial',sequence:1},{label:'After <change>',value:950,relation:'decreased',sequence:2}],
 candidates:[{candidate_id:'candidate',offset:17,width:2,endian:'little',encoding:'binary',signed:false,model:'exact',bias:0,values:[1000,950,950]}],next_experiment:'Probe a candidate.'};
function fixture(){
 const actions={},drafts={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},runtime:{game_sha256:'sha'}};
 const ctx={state,use:rows=>Object.assign(actions,rows),draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,
 sourceParams:()=>({project_id:state.project.project_id,artifact_id:state.artifact.artifact_id}),render:async()=>{},notify(){},api:{call:async()=>structuredClone(result)}};
 return {ctx,state,actions,drafts};
}
globalThis.document={getElementById:id=>({value:({'series-title':'A number','series-value':'950','series-offset':'16','series-length':'4','series-label':'Changed','series-relation':'decreased','series-delta':''})[id]??''})};
{
 const {ctx,state,actions,drafts}=fixture();await investigationSeries(ctx);await actions['series-start']();
 const html=await investigationSeries(ctx);assert.match(html,/A &lt;number&gt;/);assert.match(html,/After &lt;change&gt;/);
 assert.match(html,/0x11/);assert.match(html,/1000.*950/);assert.match(html,/correlat|hypothes/i);
 assert.match(html,/unchanged.*control/i);assert.equal(drafts['investigation-id'],'e');
 assert.match(html,/Investigate accesses/);
 const oldCall=ctx.api.call;ctx.api.call=async operation=>operation==='investigations.probe'?{
  ok:true,source_sha256:'sha',artifact_id:'a',candidate:result.candidates[0],investigation_id:'e'}:oldCall(operation);
 await actions['series-probe']({dataset:{id:'candidate'}});
 assert.equal(state.nativeProbe.result.candidate.candidate_id,'candidate');
 assert.doesNotMatch(html,/Edit ROM directly|Verified stat/);
 state.artifact={artifact_id:'same-bytes-other-source',sha256:'sha'};
 await assert.rejects(actions['series-capture'](),/selected|changed|source/i);
 assert.doesNotMatch(await investigationSeries(ctx),/A &lt;number&gt;/);
}
{
 const {ctx,state,actions,drafts}=fixture();let finish;ctx.api.call=()=>new Promise(resolve=>finish=resolve);
 await investigationSeries(ctx);const pending=actions['series-start']();state.runtime={game_sha256:'sha',newSession:true};finish(result);await pending;
 assert.equal(drafts['investigation-id'],undefined,'A late native capture must not attach to a new runtime.');
}
{
 const {ctx,actions,state}=fixture();const pending=[];ctx.api.call=()=>new Promise(resolve=>pending.push(resolve));
 await investigationSeries(ctx);const first=actions['series-start'](),second=actions['series-start']();
 pending[1]({...result,title:'Newer'});await second;pending[0]({...result,title:'Older'});await first;
 assert.match(await investigationSeries(ctx),/Newer/);assert.doesNotMatch(await investigationSeries(ctx),/Older/);
 state.investigationSeries.result={...result,runtime_trusted:false};assert.match(await investigationSeries(ctx),/historical/i);
 await assert.rejects(actions['series-capture'](),/historical/i);
}
{
 const {ctx,drafts}=fixture();drafts['investigation-id']='e';let calls=0;ctx.api.call=async()=>{calls++;return result;};
 assert.match(await investigationSeries(ctx),/A &lt;number&gt;/);await investigationSeries(ctx);assert.equal(calls,1);
 ctx.state.runtime=null;assert.match(await investigationSeries(ctx),/Playtest/);
 releaseProjectResources(ctx.state);assert.equal(ctx.state.investigationSeries,null,'Closing a project releases investigation UI data.');
}
console.log('Universal investigation UI preserves evidence, scope, history and native-session boundaries.');
