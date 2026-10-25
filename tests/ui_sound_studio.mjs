import assert from 'node:assert/strict';
import {WavPreview,stageNote} from '../romancer/ui/sound_preview.js';
const doc={songs:[{id:'s',count:2,events:[{note:60,duration:30,volume:96},{note:64,duration:30,volume:96}]}]};
assert.deepEqual(stageNote(doc,[],'s',0,'note',67),[{kind:'note',song_id:'s',index:0,field:'note',value:67}]);
assert.deepEqual(stageNote(doc,stageNote(doc,[],'s',0,'note',67),'s',0,'note',60),[]);
assert.throws(()=>stageNote(doc,[],'s',0,'note',200));assert.throws(()=>stageNote(doc,[],'other',0,'note',60));
// Native evidence has its own `scope`; it must not overwrite selection ownership.
const soundView=await import('../romancer/ui/views/sound.js'),handlers={};let html='';
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',name:'Original.gba',system_id:'gba'},results:{},runtime:{game_sha256:'sha'}};
globalThis.document={getElementById:id=>id==='sound-frames'?{value:'120'}:null};
const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:'a'}),draft:(_id,fallback)=>fallback,
 use:next=>Object.assign(handlers,next),api:{call:async()=>({hardware:{name:'GBA',channels:[],references:[],sample_formats:['pcm-s8']},driver:{name:'Unknown',status:'UNKNOWN'}})},
 run:async()=>({ok:true,scope:'native_sound_preview',wav_base64:'UklGRnRlc3RXQVZFZGF0YQ==',frame:{sha256:'frame'},sample_frames:4,sample_rate:8000,channels:2,preview_scope:'Measured native mixed stereo output.'}),
 render:async()=>{html=await soundView.render(ctx);}};
await ctx.render();await handlers['sound-capture']();assert.match(html,/<h3>Audio preview<\/h3>/);assert.equal(state.soundPreview.scope,'native_sound_preview');
state.artifact={...state.artifact,artifact_id:'b'};await ctx.render();assert.doesNotMatch(html,/<h3>Audio preview<\/h3>/);
const soundDoc={...doc,document_id:'sd',source_sha256:'sha',definition:{},samples:[]},drafts=new Map();state.artifact.artifact_id='a';state.results['sound.inspect']=soundDoc;
ctx.draft=(key,fallback)=>drafts.get(key)??fallback;ctx.setDraft=(key,value)=>drafts.set(key,value);ctx.projectParams=()=>({project_id:'p'});ctx.notify=()=>{};
const note=value=>({kind:'note',song_id:'s',index:0,field:'note',value});
drafts.set('sound-changes',JSON.stringify({document_id:'sd',changes:[note(61)]}));await ctx.render();
state.pending={kind:'sound',artifact_id:'a',document_id:'sd',plan_id:'plan',changes:JSON.stringify([note(61)])};let finish;
ctx.run=()=>new Promise(resolve=>finish=resolve);const building=handlers['sound-build']();drafts.set('sound-changes',JSON.stringify({document_id:'sd',changes:[note(62)]}));finish({ok:true});await building;
assert.equal(JSON.parse(drafts.get('sound-changes')).changes[0]?.value,62,'build completion preserves a newer sound draft');
drafts.set('sound-changes',JSON.stringify({document_id:'sd',changes:[note('<button data-action="sound-discard">Injected</button>')]}));await ctx.render();
assert.doesNotMatch(html,/<td><button/,'restored drafts cannot introduce active HTML');assert.match(html,/Saved audio edits/);
drafts.set('sound-changes',JSON.stringify({document_id:'sd',changes:[note(62)]}));await ctx.render();
const planning=handlers['sound-plan']();state.results['sound.inspect']={...soundDoc,document_id:'sd-new'};drafts.set('sound-changes',JSON.stringify({document_id:'sd-new',changes:[note(62)]}));await ctx.render();finish({ok:true,plan_id:'old-plan'});await planning;
assert.equal(state.pending,null,'a review for an old sound definition cannot authorize the new definition');
state.pending={kind:'sound',artifact_id:'a',document_id:'sd',plan_id:'old-plan',changes:JSON.stringify([note(62)])};await ctx.render();await assert.rejects(handlers['sound-build'](),/Review/);
const closed=[],player=new WavPreview({create:()=> 'blob:owned',revoke:url=>closed.push(url)}),audio={pause(){closed.push('pause');},removeAttribute(name){closed.push(name);},load(){closed.push('load');}};
player.attach(audio,Buffer.from('RIFFtestWAVEdata').toString('base64'));assert.equal(audio.src,'blob:owned');player.close();player.close();assert.deepEqual(closed,['pause','src','load','blob:owned']);
console.log('Sound note drafts reject unknown formats and preview disposal releases playback and its owned URL.');

// An upload must merge with the latest draft, even across multiple rerenders.
const sampleDoc={...soundDoc,samples:[{id:'sample',name:'Sample',sample_count:2,duration_seconds:1,codec:'pcm-u8'}]};
state.results['sound.inspect']=sampleDoc;drafts.set('sound-changes',JSON.stringify({document_id:'sd',changes:[note(61)]}));
const inputs={'sound-operation':{value:'replace_wav'},'sound-gain':{value:'100'},'sound-wav':{files:[{size:100}]},'sound-event':{value:'0'},'sound-note-field':{value:'note'},'sound-note-value':{value:'62'}};
globalThis.document={getElementById:id=>inputs[id]||null};let finishUpload;ctx.api.uploadInput=()=>new Promise(resolve=>finishUpload=resolve);
await ctx.render();const upload=handlers['sound-sample-stage']();await handlers['sound-note-stage']();inputs['sound-note-value'].value='63';await handlers['sound-note-stage']();finishUpload({input_id:'a'.repeat(32)});await upload;
assert.equal(JSON.parse(drafts.get('sound-changes')).changes.find(c=>c.kind==='note').value,63);
const staleUpload=handlers['sound-sample-stage']();state.results['sound.inspect']={...sampleDoc,document_id:'replacement-definition'};const freshDraft=JSON.stringify({document_id:'replacement-definition',changes:[note(64)]});drafts.set('sound-changes',freshDraft);await ctx.render();finishUpload({input_id:'b'.repeat(32)});await staleUpload;assert.equal(drafts.get('sound-changes'),freshDraft);

state.results['sound.inspect']=sampleDoc;drafts.set('sound-changes',JSON.stringify({document_id:'sd',changes:[]}));inputs['sound-operation'].value='replace_wav';await ctx.render();const olderUpload=handlers['sound-sample-stage']();await handlers['sound-note-stage']();inputs['sound-operation'].value='gain';inputs['sound-gain'].value='200';await handlers['sound-sample-stage']();finishUpload({input_id:'c'.repeat(32)});await olderUpload;assert.equal(JSON.parse(drafts.get('sound-changes')).changes.find(c=>c.kind==='sample').operation,'gain');
