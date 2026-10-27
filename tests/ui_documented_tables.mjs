import assert from 'node:assert/strict';import fs from 'node:fs';
const path=new URL('../romancer/ui/documented_tables.js',import.meta.url);assert(fs.existsSync(path),'Users need a working named-table locator.');
const {documentedTables}=await import(path),actions={},calls=[],state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',system_id:'gba'},results:{}};
const candidate={candidate_id:'c',name:'Species stats',offset:4096,count:151,stride:28,status:'STRUCTURAL_MATCH',note:'Pattern lead'};
const ctx={state,use:h=>Object.assign(actions,h),sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),render:async()=>{},navigate:async name=>calls.push(['navigate',name]),run:async(op,p)=>{calls.push([op,p]);return op==='documented.scan'?{ok:true,artifact_id:'a',source_sha256:'sha',candidates:[candidate]}:{ok:true,artifact_id:'a',source_sha256:'sha',definition:{},inspection:{},note:'Pattern lead'};}};
assert.match(documentedTables(ctx),/Find game tables/);await actions['documented-scan']();assert.match(documentedTables(ctx),/151 records/);
await actions['documented-open']({dataset:{id:'c'}});assert.equal(state.tableProposal.result.note,'Pattern lead');assert.deepEqual(calls.at(-1),['navigate','tables']);
console.log('Named-table discovery opens a checked proposal without silently saving or building.');
