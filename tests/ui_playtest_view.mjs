import assert from 'node:assert/strict';
import {render} from '../romancer/ui/views/playtest.js';
globalThis.localStorage={getItem:()=>null};
const ctx={state:{artifact:{artifact_id:'a',name:'Original',sha256:'a'.repeat(64),system_id:'gb'},project:{project_id:'p',containers:[]},runtime:{session_dir:'session'},capabilities:{platform:'Windows'},results:{}},use(){},draft:(id,fallback)=>fallback,api:{call:async operation=>operation==='saves.list'?{saves:[]}:operation==='runtime.checkpoints'?{checkpoints:[]}:{profile:null}},sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'})};
const html=await render(ctx);assert.match(html,/id="runtime-screen"/,'loaded first Play needs a canvas before the first frame arrives');
console.log('A loaded session has a video surface before its first live packet.');

const sha='a'.repeat(64),core='c'.repeat(64);
const ready={...ctx,state:{...ctx.state,runtime:null,profileFamily:'gb',profileLoadedFamily:'gb',profile:{core_identity:{sha256:core},input_map:{}}},api:{call:async operation=>operation==='saves.list'?{saves:[]}:operation==='runtime.checkpoints'?{checkpoints:[{snapshot_id:'matching',game_sha256:sha,core_sha256:core,run_mode:'cold_boot'},{snapshot_id:'wrong-game',game_sha256:'b'.repeat(64),core_sha256:core},{snapshot_id:'wrong-core',game_sha256:sha,core_sha256:'d'.repeat(64)}]}:{ok:true}}};
const available=await render(ready);
assert.match(available,/READY TO LOAD/,'a valid saved setup must not say CORE REQUIRED');
assert.match(available,/value="matching"/);
assert.doesNotMatch(available,/value="wrong-game"|value="wrong-core"/,'checkpoints must match selected ROM and core');
console.log('Ready setup and source/core-filtered checkpoint choices.');

const running={...ready,state:{...ready.state,runtime:{session_dir:'active',game_sha256:sha,core_sha256:'d'.repeat(64)}}};
const runningHtml=await render(running);
assert.match(runningHtml,/value="wrong-core"/,'the running core determines checkpoint compatibility');
assert.doesNotMatch(runningHtml,/value="matching"/,'a changed saved setup must not replace the active core identity');

let focusActions={};const focusCtx={...ctx,state:{...ctx.state},use:handlers=>Object.assign(focusActions,handlers),render:async()=>{}};
const normal=await render(focusCtx);assert.match(normal,/Expand game/,'loaded playtest can give the game the full workspace width');
await focusActions['runtime-view']();assert.equal(focusCtx.state.playtestExpanded,true);
const expanded=await render(focusCtx);assert.match(expanded,/playtest-expanded/);assert.match(expanded,/Show setup/);
assert.ok(expanded.indexOf('Save state')<expanded.indexOf('playtest-setup'),'Save state remains in the game panel when setup is hidden');
assert.ok(expanded.indexOf('Load state')<expanded.indexOf('playtest-setup'),'Load state remains in the game panel');
assert.match(expanded,/Controller &amp; frame tools|Controller & frame tools/,'manual frame tools are optional');
await focusActions['runtime-view']();assert.equal(focusCtx.state.playtestExpanded,false);
console.log('Expanded game view is reversible and keeps setup accessible.');
const closedHtml=await render({...ready,state:{...ready.state,playtestExpanded:true,runtime:null}});
assert.doesNotMatch(closedHtml,/class="grid-two playtest-layout playtest-expanded"/,'closing or switching games must reveal setup and Load game');
let restoreActions={},restoreCalls=[];globalThis.document={getElementById:()=>({value:'matching'})};
const restoreCtx={...ready,state:{...ready.state,runtime:{session_dir:'loaded'}},use:handlers=>Object.assign(restoreActions,handlers),render:async()=>{},notify(){},run:async op=>{restoreCalls.push(op);return op==='runtime.load_state'?{run_mode:'imported_save_state'}:op==='runtime.capture'?{width:1,height:1,index:1}:{};}};
await render(restoreCtx);await restoreActions['runtime-restore']();
assert.deepEqual(restoreCalls,['runtime.load_state','runtime.advance','runtime.capture']);assert.equal(restoreCtx.state.runtime.run_mode,'imported_save_state');assert.equal(restoreCtx.state.frame.index,1);
console.log('Save/load controls stay visible and loading refreshes a real paused frame.');
const otherSetup={...ready,state:{...ready.state,runtime:{session_dir:'loaded',game_sha256:sha,core_sha256:core,loaded:{runtime_identity_sha256:'actual-setup'}}}};
assert.doesNotMatch(await render(otherSetup),/value="matching"/,'actual nested runtime load identity must hide states from different setup/BIOS');
