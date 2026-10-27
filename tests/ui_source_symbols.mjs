import assert from 'node:assert/strict';
import {sourceSymbols} from '../romancer/ui/source_symbols.js';
const actions={},calls=[],state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',system_id:'gba'}};
const ctx={state,draft:(_,fallback)=>fallback,sourceParams:()=>({project_id:'p',artifact_id:'a'}),use:h=>Object.assign(actions,h),api:{call:async()=>({ok:true,artifact_id:'a',source_sha256:'s',configured:true,page:0,total:2,symbols:[{name:'Stats',address:0x08001000,bank:null,file_offset:4096,reason:'ROM'},{name:'Party',address:0x02000000,bank:null,file_offset:null,reason:'RAM'}]})},navigate:async n=>calls.push(n),render:async()=>{}};
const html=await sourceSymbols(ctx);assert.match(html,/Stats/);assert.match(html,/Party/);assert.equal((html.match(/data-action="symbol-bytes"/g)||[]).length,1);
await actions['symbol-bytes']({dataset:{id:'4096'}});assert.equal(state.resourceJump,4096);assert.equal(calls[0],'resources');
state.artifact={...state.artifact,artifact_id:'other'};await actions['symbol-bytes']({dataset:{id:'4096'}});assert.equal(calls.length,1);
console.log('Symbol navigation exposes ROM bytes, keeps RAM separate and refuses stale selection.');
