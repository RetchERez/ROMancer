import assert from 'node:assert/strict';
import {buildChecks} from '../romancer/ui/build_checks.js';
const handlers={},calls=[],state={project:{project_id:'p',sources:[{artifact_id:'a',name:'Original'}],builds:[{artifact_id:'b',name:'Build'}]},artifact:{artifact_id:'a',sha256:'s'},page:'gameview'};
const config={name:'Opening',automatic:true,mode:'review_changes',steps:[{frames:600,buttons:[],port:0},{frames:420,buttons:[],port:0}],region:null,route_ids:[]};
const ctx={state,draft:(_,d)=>d,use:h=>Object.assign(handlers,h),sourceParams:()=>({project_id:'p',artifact_id:'a'}),api:{call:async()=>({ok:true,artifact_id:'a',source_sha256:'s',baseline_id:'a',config,configured:true,pending:[],results:[]})},run:async(op,p)=>calls.push([op,p]),render:async()=>{}};
const html=await buildChecks(ctx);assert.match(html,/Frames before capture/);
const values={'check-name':'Simple check','check-mode':'unchanged','check-input-mode':'simple','check-frames':'700','check-steps':'INVALID JSON'};globalThis.document={getElementById:id=>({value:values[id]||'',checked:id==='check-auto'})};
await handlers['check-save']();assert.equal(calls[0][0],'checks.configure');assert.deepEqual(calls[0][1].config.steps,[{frames:600,buttons:[],port:0},{frames:100,buttons:[],port:0}]);
console.log('Beginners configure automatic checks with frame count and mode, without writing JSON.');
