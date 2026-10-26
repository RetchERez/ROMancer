import assert from 'node:assert/strict';
import * as view from '../romancer/ui/views/sound.js';

function wav(values,rate=8000){
 const bytes=Buffer.alloc(44+values.length*2);bytes.write('RIFF');bytes.writeUInt32LE(bytes.length-8,4);bytes.write('WAVEfmt ',8);bytes.writeUInt32LE(16,16);bytes.writeUInt16LE(1,20);bytes.writeUInt16LE(1,22);bytes.writeUInt32LE(rate,24);bytes.writeUInt32LE(rate*2,28);bytes.writeUInt16LE(2,32);bytes.writeUInt16LE(16,34);bytes.write('data',36);bytes.writeUInt32LE(values.length*2,40);values.forEach((value,i)=>bytes.writeInt16LE(value,44+i*2));return bytes.toString('base64');
}
const originalWav=wav([-10000,20000]),editedWav=wav([0,0]);
const packet=encoded=>({ok:true,wav_base64:encoded,sample_rate:8000,sample_frames:2,channels:1,preview_scope:'Decoded mono sample.'});
const doc={ok:true,document_id:'d',source_sha256:'sha',definition:{schema_version:1},samples:[{id:'s',name:'Sample',sample_count:2,duration_seconds:.00025,codec:'pcm-s16le',peaks:[[1,2]]},{id:'other',name:'Other',sample_count:2,duration_seconds:.00025,codec:'pcm-s16le',peaks:[[3,4]]}],songs:[{id:'song',name:'Song',driver_scope:'Identified fixture',events:[{note:60,duration:30,volume:96}]}]};
const drafts=new Map(),handlers={},inputs={
 'sound-operation':{value:'silence'},'sound-gain':{value:'100'},'sound-event':{value:'0'},'sound-note-field':{value:'note'},'sound-note-value':{value:'62'},'sound-transpose':{value:'1'}
};
globalThis.document={getElementById:id=>inputs[id]||null};
const state={page:'sound',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',name:'Original.gb',system_id:'gb'},results:{'sound.inspect':doc}};
let html='',requests=[],reply=async p=>packet(p.changes.length?editedWav:originalWav);
const hardware={name:'GB',channels:[],references:[],sample_formats:['pcm-s16le']};
const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),draft:(key,fallback)=>drafts.get(key)??fallback,setDraft:(key,value)=>drafts.set(key,value),use:next=>Object.assign(handlers,next),notify(){},api:{call:async(op,p)=>{if(op==='sound.system')return {hardware,driver:{name:'Identified',status:'IDENTIFIED',references:[]}};assert.equal(op,'sound.preview');requests.push(structuredClone(p));return reply(p);}},render:async()=>{html=await view.render(ctx);}};
await ctx.render();await handlers['sound-sample-stage']();
assert.equal(requests.length,2,'staging a supported sample requests original and edited audio automatically');
assert.deepEqual(requests.map(r=>r.changes.length),[0,1]);
assert.deepEqual(state.soundPreview.comparison.original.peaks,[[-10000,-10000],[20000,20000]],'original waveform comes from original PCM, not stale inspection peaks');
assert.deepEqual(state.soundPreview.comparison.edited.peaks,[[0,0],[0,0]],'edited waveform comes from exact returned PCM');
assert.equal(state.soundPreview.comparison.changed,true);
assert.match(html,/Original/);assert.match(html,/Edited/);assert.match(html,/Preview updated/);assert.doesNotMatch(html,/autoplay/);
assert.doesNotMatch(html,/<details class="config" open><summary>Source-bound sound definition/);

// Replacing a preview closes its player immediately and never starts playback.
const lifecycle=[];state.soundPlayer={close:()=>lifecycle.push('close')};
await handlers['sound-note-stage']();assert.deepEqual(lifecycle,['close']);
assert.equal(requests.at(-1).kind,'song');assert.equal(requests.at(-1).resource_id,'song');
assert.equal(requests.at(-1).changes.find(c=>c.kind==='note').value,62);
await handlers['sound-transpose']();assert.equal(requests.at(-1).changes.find(c=>c.kind==='note').value,63);

// A later request owns the UI even when the earlier decode finishes last.
const deferred=[];reply=p=>new Promise((resolve,reject)=>deferred.push({p,resolve,reject}));
const older=handlers['sound-sample-preview']();await new Promise(setImmediate);
inputs['sound-operation'].value='gain';inputs['sound-gain'].value='200';const newer=handlers['sound-sample-stage']();await new Promise(setImmediate);
assert.equal(deferred.length,4);
deferred[2].resolve(packet(originalWav));deferred[3].resolve(packet(editedWav));await newer;
const newest=state.soundPreview;
deferred[0].resolve(packet(wav([30000,30000])));deferred[1].resolve(packet(wav([30000,30000])));await older;
assert.equal(state.soundPreview,newest,'an old completion cannot replace the newer edit preview');

// Changes of sample, source, document or draft invalidate in-flight data.
for(const mutation of [
 ()=>drafts.set('sound-sample','other'),
 ()=>{state.artifact={...state.artifact,artifact_id:'b'};},
 ()=>{state.results['sound.inspect']={...doc,document_id:'replacement'};},
 ()=>drafts.set('sound-changes',JSON.stringify({document_id:'d',changes:[]}))
]){
 state.artifact={...state.artifact,artifact_id:'a'};state.results['sound.inspect']=doc;drafts.delete('sound-sample');drafts.set('sound-changes',JSON.stringify({document_id:'d',changes:[{kind:'sample',sample_id:'s',operation:'silence',value:0,wav_base64:null}]}));
 await ctx.render();const start=deferred.length,pending=handlers['sound-sample-preview']();await new Promise(setImmediate);mutation();
 deferred[start].resolve(packet(originalWav));deferred[start+1].resolve(packet(editedWav));await pending;
 assert.equal(state.soundPreview,null,'changed ownership must not install old audio');
 await ctx.render();assert.doesNotMatch(html,/id="edited-waveform"/,'invalidated audio must not appear under an Edited label');
}

state.artifact={...state.artifact,artifact_id:'a'};state.results['sound.inspect']=doc;drafts.delete('sound-sample');await ctx.render();
reply=async()=>{throw Error('Decoder unavailable');};await handlers['sound-sample-preview']();
assert.match(html,/Preview unavailable: Decoder unavailable/);assert.doesNotMatch(html,/id="edited-waveform"|id="sound-player"/);
reply=async()=>packet('UklGRnRlc3RXQVZFZGF0YQ==');await handlers['sound-sample-preview']();
assert.match(html,/Preview unavailable/);assert.equal(state.soundPreview,null,'malformed WAV cannot retain an edited waveform');
reply=async p=>({...packet(p.changes.length?editedWav:originalWav),source_sha256:'different-source'});await handlers['sound-sample-preview']();
assert.equal(state.soundPreview,null,'a response identifying another source must not install audio');assert.match(html,/Preview unavailable/);

// Mount real returned PCM into both waveform surfaces and dispose each owned URL.
reply=async p=>packet(p.changes.length?editedWav:originalWav);inputs['sound-operation'].value='silence';await handlers['sound-sample-stage']();
const lines={original:[],edited:[]},canvas=name=>({width:720,height:140,getContext:()=>({fillRect(){},beginPath(){},moveTo(x,y){lines[name].push(y);},lineTo(x,y){lines[name].push(y);},stroke(){}})}),audioCalls=[],audio={pause(){audioCalls.push('pause');},removeAttribute(){},load(){},play(){throw Error('Preview must never autoplay');}},urls=[];
inputs['sound-player']=audio;inputs['original-waveform']=canvas('original');inputs['edited-waveform']=canvas('edited');
const create=URL.createObjectURL,revoke=URL.revokeObjectURL;URL.createObjectURL=()=> 'blob:sound-owned';URL.revokeObjectURL=url=>urls.push(url);
view.mount(ctx);assert.equal(audio.src,'blob:sound-owned');assert(lines.original.some(y=>y!==70));assert(lines.edited.every(y=>y===70));
view.mount(ctx);assert.deepEqual(urls,['blob:sound-owned']);assert.deepEqual(audioCalls,['pause']);state.soundPlayer.close();
URL.createObjectURL=create;URL.revokeObjectURL=revoke;

state.results['sound.inspect']={...doc,songs:[]};await ctx.render();const previous=requests.length;
await assert.rejects(async()=>handlers['sound-note-stage'](),/No supported music driver/);assert.equal(requests.length,previous);
assert.match(html,/No supported sequence driver/);
console.log('Staged sound edits decode original/edited PCM automatically, reject stale completions, dispose players, and expose failures without stale waveforms.');
