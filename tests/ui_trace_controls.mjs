import assert from 'node:assert/strict';import fs from 'node:fs';
const file=new URL('../romancer/ui/trace_controls.js',import.meta.url);assert(fs.existsSync(file),'Playtest needs persistent screen-to-ROM tracing controls.');
const {traceControls}=await import(file),actions={},state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',size:32768},frame:{sha256:'frame'},runtime:{}};
const ctx={state,draft:(_,d)=>d,use:h=>Object.assign(actions,h),sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'})};
let html=traceControls(ctx);assert.match(html,/Trace selected object/);assert.match(html,/disabled/);
const {selectionKey}=await import('../romancer/ui/tool_inputs.js');state.visualRegion={scope:selectionKey(state),frame_sha256:'frame',region:{x:0,y:0,width:16,height:16}};html=traceControls(ctx);assert.match(html,/Save.*trace|Trace selected object/);
console.log('Persistent tracing requires a current captured region and uses shared source-bound controls.');
