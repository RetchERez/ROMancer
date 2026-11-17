import {esc,field,select,button,json,read} from './common.js';
import {getSettings} from './app_settings.js';
import {selectionKey} from './tool_inputs.js';

export async function loadPlaytestGame(ctx,system_id,content,message='Game loaded. Press Play.'){
 const {state}=ctx,scope=selectionKey(state);
 state.liveMuted=getSettings().startMuted;
 ctx.setDraft?.('runtime-volume',String(getSettings().volume));
 const isDisc=content.startsWith('disc:');
 const target=isDisc?{container_id:content.slice(5)}:{artifact_id:content};
 const loaded=await ctx.run(isDisc?'runtime.load_disc':'runtime.load_profile',
  {...ctx.projectParams(),...target,system_id},{refresh:false,render:false});
 if(scope!==selectionKey(state))return;
 state.runtime=loaded;
 state.frame=null;
 if(state.page==='playtest'){
  await ctx.render();
  ctx.notify(message);
 }
}
const families=[['nes','NES'],['snes','SNES'],['genesis','Genesis'],['gb','Game Boy'],['gbc','Game Boy Color'],['sms','Master System']];
const defaultKeys={up:'ArrowUp',down:'ArrowDown',left:'ArrowLeft',right:'ArrowRight',a:'z',b:'x',x:'a',y:'s',l:'q',r:'w',start:'Enter',select:'Shift'};
export async function runtimeSetup(ctx){const {state}=ctx,family=state.profileFamily||state.artifact?.system_id||'nes';
 if(state.profileLoadedFamily!==family){const saved=await ctx.api.call('profiles.get',{system_id:family});state.profile=saved.profile;state.profileEngine=saved.engine||'';state.profileLoadedFamily=family;}
 const profile=state.profile;let available=false,setupError='';if(profile){try{const checked=await ctx.api.call('profiles.validate',{system_id:family});available=checked.ok;}catch(error){setupError=error.message;}}
 const running=state.runtime?.loaded?.loaded;
 const tilt=running?.core_options?.romancer_mbc7_tilt==='dpad-v1';
 state.profileAvailable=available;
 const candidates=(state.results['profiles.scan_local']?.candidates||[]).filter(row=>row.systems.includes(family));
 ctx.use({'profile-scan':()=>ctx.run('profiles.scan_local',{directories:[]},{refresh:false}),
 'profile-auto':async node=>{const candidate=candidates.find(row=>row.candidate_id===node.dataset.id);if(!candidate)throw new Error('Scan local cores and choose a result.');const result=await ctx.run('profiles.configure_local',{system_id:family,candidate},{refresh:false,render:false});state.profile=result.profile;state.profileLoadedFamily=family;await ctx.render();ctx.notify('Ready to load this system.');},
 'profile-open':async()=>{state.profileFamily=read('profile-family');state.profileLoadedFamily=null;const result=await ctx.api.call('profiles.get',{system_id:state.profileFamily});state.profile=result.profile;state.profileEngine=result.engine||'';state.profileLoadedFamily=state.profileFamily;if(result.profile){ctx.setDraft('core-path',result.profile.core);ctx.setDraft('core-options',JSON.stringify(result.profile.options,null,2));ctx.setDraft('system-path',result.profile.system_dir||'');for(const [key,value] of Object.entries(result.profile.input_map))ctx.setDraft('key-'+key,value);}await ctx.render();},
 'profile-save':async()=>{if(read('profile-family')!==state.profileLoadedFamily)throw new Error('Load settings for the selected system before saving.');const input_map=Object.fromEntries(Object.keys(defaultKeys).map(k=>[k,read('key-'+k)]));const result=await ctx.run('profiles.save',{system_id:read('profile-family'),core:read('core-path'),options:json('core-options'),system_dir:read('system-path').trim()||null,input_map},{refresh:false,render:false});state.profile=result.profile;state.profileFamily=result.profile.system_id;state.profileEngine='';state.profileLoadedFamily=result.profile.system_id;ctx.notify('System setup saved.');await ctx.render();},
 'profile-validate':()=>ctx.run('profiles.validate',{system_id:read('profile-family')},{refresh:false}),
 'profile-option':()=>{const key=read('option-key'),value=read('option-value');if(!key)throw new Error('Enter an option name.');ctx.setDraft('core-options',JSON.stringify({...json('core-options'),[key]:value},null,2));return ctx.render();}
 });
 return `<p class="notice ${setupError?'warm':''}">${running?'Emulator loaded · '+esc(running.core.library_name):available?`Emulator ready${state.profileEngine?' · '+esc(state.profileEngine)+' included':''}`:profile?esc(setupError):'The source edition needs a reviewed emulator core. The full Windows download includes one.'}</p>${tilt?'<p class="notice">Directions tilt the game. Release them to hold it flat during the balance prompt.</p>':''}${!profile?`${button('Find local cores','profile-scan')}<div class="actions">${candidates.map(row=>button('Use '+row.core.split(/[\\/]/).at(-1),'profile-auto',{id:row.candidate_id})).join('')}</div>${state.results['profiles.scan_local']&&!candidates.length?'<p>No matching core found. Open Advanced setup to choose one.</p>':''}`:''}<div class="field-row">${select('profile-family','System',families,family)}${select('runtime-content','ROM or build to play',[...(state.artifact?[[state.artifact.artifact_id,state.artifact.name]]:[])],ctx.draft('runtime-content',state.artifact?.artifact_id||'disc:'+state.project.containers?.[0]?.container_id))}</div><div class="actions">${button('Load system settings','profile-open')}${button('Check setup','profile-validate')}</div><details class="config"><summary>Controller keys & advanced options</summary>${field('system-path','System-file folder (optional)',ctx.draft('system-path',profile?.system_dir||''))}<div class="field-row">${field('option-key','Option name',ctx.draft('option-key',''))}${field('option-value','Option value',ctx.draft('option-value',''))}</div>${button('Set option','profile-option')}<div class="field-row">${Object.entries(defaultKeys).map(([key,value])=>field('key-'+key,key.toUpperCase(),ctx.draft('key-'+key,profile?.input_map[key]||value))).join('')}</div></details>${button('Save emulator settings','profile-save')}`;
}


export function wavFromPCM(encoded,rate){if(!Number.isInteger(rate)||rate<1||rate>192000)throw new Error('Unsupported sample rate.');const raw=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));if(!raw.length||raw.length>1048576||raw.length%4)throw new Error('Invalid PCM capture.');const buffer=new ArrayBuffer(44+raw.length),view=new DataView(buffer),bytes=new Uint8Array(buffer);function text(offset,value){for(let i=0;i<value.length;i++)bytes[offset+i]=value.charCodeAt(i);}text(0,'RIFF');view.setUint32(4,36+raw.length,true);text(8,'WAVEfmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,2,true);view.setUint32(24,rate,true);view.setUint32(28,rate*4,true);view.setUint16(32,4,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,raw.length,true);bytes.set(raw,44);return bytes;}
let audioURL,audioNode;
export function disposeAudio(){if(audioNode){try{audioNode.pause();audioNode.removeAttribute('src');audioNode.load();}catch{}audioNode=null;}if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null;}}
export function mountAudio(record){const player=document.getElementById('pcm-player'),canvas=document.getElementById('pcm-wave');if(!player||!canvas||!record?.observed)return;disposeAudio();audioNode=player;const wav=wavFromPCM(record.pcm_s16le_base64,record.sample_rate);audioURL=URL.createObjectURL(new Blob([wav],{type:'audio/wav'}));player.src=audioURL;const prefs=getSettings();player.volume=prefs.volume/100;player.muted=prefs.startMuted;player.loop=prefs.loopPreview;const samples=new DataView(wav.buffer,44),frames=(wav.length-44)/4,context=canvas.getContext('2d');context.fillStyle='#101b20';context.fillRect(0,0,canvas.width,canvas.height);context.strokeStyle='#76dbc3';context.beginPath();for(let x=0;x<canvas.width;x++){const frame=Math.min(frames-1,Math.floor(x/canvas.width*frames)),value=samples.getInt16(frame*4,true)/32768,y=canvas.height/2-value*canvas.height*.45;if(x)context.lineTo(x,y);else context.moveTo(x,y);}context.stroke();}
