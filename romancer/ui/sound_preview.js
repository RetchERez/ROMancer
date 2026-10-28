import {getSettings} from './app_settings.js';
export class WavPreview{
 constructor(urls={create:blob=>URL.createObjectURL(blob),revoke:url=>URL.revokeObjectURL(url)}){this.urls=urls;this.audio=null;this.url=null;}
 attach(audio,encoded){this.close();if(typeof encoded!=='string'||encoded.length>6*1024*1024)throw Error('Audio preview exceeds its byte budget.');const raw=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));if(String.fromCharCode(...raw.slice(0,4))!=='RIFF'||String.fromCharCode(...raw.slice(8,12))!=='WAVE')throw Error('Preview is not a WAV file.');this.url=this.urls.create(new Blob([raw],{type:'audio/wav'}));this.audio=audio;audio.src=this.url;const prefs=getSettings();audio.volume=prefs.volume/100;audio.muted=prefs.startMuted;audio.loop=prefs.loopPreview;}
 close(){if(this.audio){try{this.audio.pause();this.audio.removeAttribute('src');this.audio.load();}catch{}this.audio=null;}if(this.url){this.urls.revoke(this.url);this.url=null;}}
}
function decodedWav(encoded){
 if(typeof encoded!=='string'||encoded.length>6*1024*1024)throw Error('Audio preview exceeds its byte budget.');
 const raw=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)),view=new DataView(raw.buffer),tag=at=>String.fromCharCode(...raw.slice(at,at+4));
 if(raw.length<44||tag(0)!=='RIFF'||tag(8)!=='WAVE'||view.getUint32(4,true)+8!==raw.length)throw Error('Decoded preview is not a complete PCM WAV.');
 let format=null,pcm=null,chunks=0;
 for(let at=12;at+8<=raw.length;){
  if(++chunks>1024)throw Error('WAV chunk budget exceeded.');const size=view.getUint32(at+4,true),start=at+8,end=start+size;
  if(end>raw.length)throw Error('Decoded WAV contains a truncated chunk.');
  if(tag(at)==='fmt '){if(size<16)throw Error('Decoded WAV format is incomplete.');format={codec:view.getUint16(start,true),channels:view.getUint16(start+2,true),sample_rate:view.getUint32(start+4,true),block:view.getUint16(start+12,true),bits:view.getUint16(start+14,true)};}
  if(tag(at)==='data'){if(pcm)throw Error('Decoded WAV has duplicate audio data.');pcm=raw.subarray(start,end);}
  at=end+(size%2);
 }
 if(!format||format.codec!==1||format.bits!==16||![1,2].includes(format.channels)||!format.sample_rate||format.sample_rate>384000||format.block!==format.channels*2||!pcm?.length||pcm.length%format.block)throw Error('Preview waveform requires decoded 16-bit mono or stereo PCM.');
 return {pcm,channels:format.channels,sample_rate:format.sample_rate,frames:pcm.length/format.block};
}
function waveform(decoded){
 const {pcm,channels,sample_rate,frames}=decoded,view=new DataView(pcm.buffer,pcm.byteOffset,pcm.byteLength),step=Math.max(1,Math.ceil(frames/512)),peaks=[];
 for(let first=0;first<frames;first+=step){let low=32767,high=-32768;for(let i=first*channels;i<Math.min(frames,first+step)*channels;i++){const value=view.getInt16(i*2,true);low=Math.min(low,value);high=Math.max(high,value);}peaks.push([low,high]);}
 return {peaks,channels,sample_rate,frames};
}
export function compareWavPreviews(original,edited){
 const before=decodedWav(original),after=decodedWav(edited),changed=before.channels!==after.channels||before.sample_rate!==after.sample_rate||before.pcm.length!==after.pcm.length||before.pcm.some((value,i)=>value!==after.pcm[i]);
 return {original:waveform(before),edited:waveform(after),changed};
}
export function drawWaveform(canvas,peaks){
 if(!canvas)return;const c=canvas.getContext('2d'),middle=canvas.height/2,amplitude=Math.max(0,middle-5);c.fillStyle='#102127';c.fillRect(0,0,canvas.width,canvas.height);c.strokeStyle='#73d7ba';c.beginPath();
 for(const [i,[low,high]] of peaks.entries()){const x=i/(peaks.length-1||1)*canvas.width;c.moveTo(x,middle-low/32768*amplitude);c.lineTo(x,middle-high/32768*amplitude);}c.stroke();
}
function sameOperand(song,change,index,field){
 if(change.kind!=='note'||change.song_id!==song.id||change.field!==field)return false;
 if(change.index===index)return true;
 const offset=song.events[index]?.edit_offsets?.[field];return ['wl4-m4a-v1','wl4-m4a-v2'].includes(song.driver)&&Number.isSafeInteger(offset)&&song.events[change.index]?.edit_offsets?.[field]===offset;
}
export function soundEventValue(song,changes,index,field){return changes.find(change=>sameOperand(song,change,index,field))?.value??song.events[index][field];}
export function stageNote(doc,changes,songId,index,field,value){
 const song=doc.songs.find(s=>s.id===songId),bounds=['wl4-m4a-v1','wl4-m4a-v2'].includes(song?.driver)?{note:[0,127],volume:[0,127],channel_volume:[0,127],tempo:[1,127],pan:[0,127]}:{note:[33,108],duration:[1,6000],volume:[0,127]};
 if(['wl4-m4a-v1','wl4-m4a-v2'].includes(song?.driver)&&(!song.sequence_edit_supported||!song.events[index]?.editable_fields?.includes(field)))throw Error('This value is inherited, protected or read-only. Choose an explicit editable event.');
 if(!song||!Number.isInteger(index)||index<0||index>=song.events.length||!bounds[field]||!Number.isInteger(value)||value<bounds[field][0]||value>bounds[field][1])throw Error('Choose a supported song field and an in-range value.');
 const result=changes.filter(change=>!sameOperand(song,change,index,field));if(value!==song.events[index][field])result.push({kind:'note',song_id:songId,index,field,value});
 if(result.length>256)throw Error('Review at most256 sound changes. Create a build before staging more.');return result;
}
export function restoreSoundChanges(doc,encoded){
 if(!doc)return [];const saved=JSON.parse(encoded);if(saved?.document_id!==doc.document_id)return [];
 if(!Array.isArray(saved.changes)||saved.changes.length>256)throw Error('Saved audio edits exceed the change budget.');
 let result=[];const seen=new Set();
 for(const c of saved.changes){
  if(!c||typeof c!=='object'||Array.isArray(c))throw Error('Saved audio edits contain an invalid change.');
  const key=JSON.stringify([c.kind,c.song_id??c.sample_id,c.index,c.field]);if(seen.has(key))throw Error('Saved audio edits contain duplicate changes.');seen.add(key);
  const song=c.kind==='note'?doc.songs.find(song=>song.id===c.song_id):null;if(['wl4-m4a-v1','wl4-m4a-v2'].includes(song?.driver)&&result.some(change=>sameOperand(song,change,c.index,c.field)))throw Error('Saved audio edits contain duplicate shared-pattern changes.');
  if(c.kind==='note')result=stageNote(doc,result,c.song_id,c.index,c.field,c.value);
  else if(c.kind==='sample'){
   if(!doc.samples.some(s=>s.id===c.sample_id)||!['gain','reverse','silence','replace_wav'].includes(c.operation))throw Error('Saved audio edits reference an unsupported sample.');
   if(c.operation==='gain'&&(!Number.isInteger(c.value)||c.value<0||c.value>400))throw Error('Saved audio edits contain an invalid gain.');
   const next={kind:'sample',sample_id:c.sample_id,operation:c.operation,value:c.operation==='gain'?c.value:0,wav_base64:null};
   if(c.operation==='replace_wav'){if(typeof c.wav_input_id!=='string'||!/^[a-f0-9]{32}$/.test(c.wav_input_id)||c.wav_base64!==null)throw Error('Saved audio edits need an owned replacement WAV.');next.wav_input_id=c.wav_input_id;}
   result.push(next);
  }else throw Error('Saved audio edits contain an unsupported change.');
 }
 return result;
}
