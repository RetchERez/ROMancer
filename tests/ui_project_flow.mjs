import assert from 'node:assert/strict';
const flow=await import('../romancer/ui/project_flow.js').catch(()=>null);
assert.ok(flow,'project state and dropped-file helpers are missing');
const state={project:{project_id:'old'},artifact:{artifact_id:'rom'},runtime:{},frame:{},snapshot:{},results:{old:true},pending:{},paint:{},profileFamily:'nes',profileLoadedFamily:'nes',playing:true,heldButtons:['a'],page:'assets',drafts:{old:'large draft'},romScans:{old:{result:'large scan'}},pixelHistories:new Map([['old',{}]]),spriteHistory:{},hexDraft:{},translationSheet:{}};
const first=flow.selectionTicket(state),second=flow.selectionTicket(state);
assert.equal(flow.selectionCurrent(state,first),false);
assert.equal(flow.selectionCurrent(state,second),true);
flow.clearProjectState(state);
assert.equal(flow.selectionCurrent(state,second),false);
for(const key of ['project','artifact','runtime','frame','snapshot','pending','paint','profileFamily','profileLoadedFamily'])assert.equal(state[key],null,key);
assert.deepEqual(state.results,{});assert.deepEqual(state.heldButtons,[]);assert.equal(state.playing,false);assert.equal(state.page,'overview');
assert.deepEqual(state.drafts,{});assert.deepEqual(state.romScans,{});
for(const key of ['pixelHistories','spriteHistory','hexDraft','translationSheet'])assert.equal(state[key],null,'Closing a project releases '+key);
const file={name:'sample.gb',size:32768};assert.equal(flow.droppedSource([file]),file);
assert.throws(()=>flow.droppedSource([]),/one file/i);
assert.throws(()=>flow.droppedSource([file,file]),/one file/i);
assert.throws(()=>flow.droppedSource([{name:'huge',size:64*1024*1024+1}]),/64 MiB/);
assert.throws(()=>flow.droppedSource([{name:'empty',size:0}]),/empty/i);
assert.equal(flow.helpForError('no active playtest; load a compatible native core first').topic,'playtest');
assert.equal(flow.helpForError('source revision changed').topic,'recovery');
assert.equal(flow.helpForError('fixed text slot overflow').topic,'text');
console.log('Project closing, stale selection, dropped-file limits and contextual error help passed.');

// A failed save must keep the only pending edit and block source/project changes.
assert.equal(typeof flow.DraftQueue,'function');
let diskFull=true,saved=[],notices=[];
const writes=new flow.DraftQueue();
writes.enqueue('pixels',async()=>{if(diskFull)throw Error('disk full');saved.push('pixels');},error=>notices.push(error.message));
await assert.rejects(writes.flush(),/not saved|unsaved/i);
assert.throws(()=>writes.clear(),/not saved|unsaved/i);
assert.deepEqual(notices,['disk full']);
diskFull=false;writes.enqueue('pixels',async()=>saved.push('pixels'),()=>{});await writes.flush();writes.clear();
assert.deepEqual(saved,['pixels']);assert.equal(writes.pending.size,0);assert.equal(writes.failed.size,0);
let finish,secondDone=false;
writes.enqueue('one',()=>new Promise(resolve=>finish=resolve),()=>{});
const flushing=writes.flush();await Promise.resolve();
writes.enqueue('two',async()=>{secondDone=true;},()=>{});finish();await flushing;
assert.equal(secondDone,true);writes.clear();

// Exercise the real transition function: input can arrive while the core closes.
const appSource=await (await import('node:fs/promises')).readFile(new URL('../romancer/ui/app.js',import.meta.url),'utf8');
const closeSource=appSource.slice(appSource.indexOf('async function closeProject()'),appSource.indexOf('\nasync function navigate(',appSource.indexOf('async function closeProject()')));
const transitionState={project:{project_id:'p'},artifact:{artifact_id:'a'},runtime:{},drafts:{}};
const transitionWrites=new flow.DraftQueue();
const closing=new Function('state','stopPlayback','flushDrafts','api','clearProjectState','clearDraftCache','removePreference','render','rememberLocation',closeSource+';return closeProject;')(transitionState,()=>{},()=>transitionWrites.flush(),{call:async()=>{transitionState.drafts.late='painted while closing';transitionWrites.enqueue('late',async()=>{throw Error('disk full');},()=>{});}},flow.clearProjectState,()=>{transitionWrites.clear();transitionState.drafts={};},()=>{},async()=>{},()=>{});
await assert.rejects(closing(),/not saved|unsaved/i);
assert.equal(transitionState.project.project_id,'p');assert.equal(transitionState.drafts.late,'painted while closing');

// Undo must reconcile the live byte buffer as well as the stored draft value.
const moveSource=appSource.slice(appSource.indexOf('async function moveDraft('),appSource.indexOf('\nconst ctx=',appSource.indexOf('async function moveDraft(')));
const hexState={drafts:{},hexDraft:{changes:new Map([[1,'58']])},hexReview:{signature:'reviewed'},pending:{}};
const full='p:a:resources:hex-changes',revisions=new Map([[full,{revision:1}]]);
const moving=new Function('state','flushDrafts','lastDraft','draftRevisions','api','render',moveSource+';return moveDraft;')(hexState,async()=>{},{project_id:'p',artifact_id:'a',key:'resources:hex-changes',full},revisions,{call:async()=>({revision:2,value:null})},async()=>{});
await moving('undo');assert.equal(hexState.hexDraft,null);assert.equal(hexState.hexReview,null);assert.equal(hexState.drafts[full],null);
