import assert from 'node:assert/strict';
import {ensureRomScan,scanControls} from '../romancer/ui/rom_scan.js';
import {revisionControls} from '../romancer/ui/revision_controls.js';
globalThis.document={getElementById:()=>null};
let calls=[],release;
const result={ok:true,identification:{profile:null},coverage:{file_bytes_read:1024,file_size:1024,whole_file_read:true,result_limit_per_kind:100,segments:[]},catalog:{file:{status:'NO_CATALOG'}},system_id:'nes',health:{crc32:'12345678'},counts:{text:1,graphics:0,compression:0},candidates:[{kind:'text',offset:32,preview:'HELLO',confidence:'possible',format:'ascii'}],limits:[]};
const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'}},sourceParams:()=>({project_id:'p',artifact_id:ctx.state.artifact.artifact_id}),use(){},api:{call:async(op,p)=>{calls.push([op,p]);return {status:'READY',result};}}};
await ensureRomScan(ctx);await ensureRomScan(ctx);assert.equal(calls.length,1,'repeat renders reuse current scan');
const html=scanControls(ctx);assert.match(html,/game revision unknown/);assert.match(html,/HELLO/);assert.match(html,/possible/);
ctx.state.artifact={artifact_id:'b',sha256:'other'};ctx.api.call=async()=>new Promise(r=>release=r);
const old=ensureRomScan(ctx);ctx.state.artifact={artifact_id:'c',sha256:'third'};release({status:'READY',result});await old;
assert.doesNotMatch(scanControls(ctx),/HELLO/,'late scan results must not label another ROM');
console.log('Automatic scans reuse results and keep late identities/candidates bound to their selection.');
let handlers={};globalThis.document={getElementById:id=>id==='revision-file'?{files:[{}]}:{value:'file'}};
ctx.state.romScans={old:{status:'READY'}};ctx.draft=(_,fallback)=>fallback;ctx.use=map=>Object.assign(handlers,map);ctx.notify=()=>{};ctx.render=async()=>{};
ctx.api.uploadInput=async()=>({input_id:'catalog'});ctx.run=async()=>({count:1});
revisionControls(ctx);await handlers['revision-import']();assert.deepEqual(ctx.state.romScans,{},'new references invalidate the in-memory scan');

ctx.api.call=async()=>({status:'READY',result});
for(let index=0;index<100;index++){ctx.state.artifact={artifact_id:'rom-'+index,sha256:'sha-'+index};await ensureRomScan(ctx);}
assert.ok(Object.keys(ctx.state.romScans).length<=8,'Repeated source visits must not retain every large scan result.');

result.graphics_index={status:'STORAGE_CANDIDATES',codec:'tile8-planar2-msb-v1',sampled_cells:200,cell_sampling_stride:1,runtime_status:'WAITING_FOR_GAMEPLAY',banks:[{offset:16384,length:16384,sampled_nonflat_cells:120}],repeated_patterns:[{count:3,offsets:[32,64,96]}]};
assert.match(scanControls(ctx),/Graphics organization/);
assert.match(scanControls(ctx),/Waiting for gameplay/);
assert.match(scanControls(ctx),/byte-identical/i);
result.structural_lab={candidates:[{offset:32,count:5,stride:8,width:4}],total_candidates:1,
 coverage:[{offset:0,length:4096}],scope:'Sampled first 4096 bytes of each segment.'};
assert.match(scanControls(ctx),/Repeated layout hypotheses/);
assert.match(scanControls(ctx),/Investigate layout/);
