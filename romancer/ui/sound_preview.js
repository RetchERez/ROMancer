export class WavPreview{
 constructor(urls={create:blob=>URL.createObjectURL(blob),revoke:url=>URL.revokeObjectURL(url)}){this.urls=urls;this.audio=null;this.url=null;}
 attach(audio,encoded){this.close();if(typeof encoded!=='string'||encoded.length>6*1024*1024)throw Error('Audio preview exceeds its byte budget.');const raw=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));if(String.fromCharCode(...raw.slice(0,4))!=='RIFF'||String.fromCharCode(...raw.slice(8,12))!=='WAVE')throw Error('Preview is not a WAV file.');this.url=this.urls.create(new Blob([raw],{type:'audio/wav'}));this.audio=audio;audio.src=this.url;}
 close(){if(this.audio){try{this.audio.pause();this.audio.removeAttribute('src');this.audio.load();}catch{}this.audio=null;}if(this.url){this.urls.revoke(this.url);this.url=null;}}
}
export function stageNote(doc,changes,songId,index,field,value){const song=doc.songs.find(s=>s.id===songId),bounds={note:[33,108],duration:[1,6000],volume:[0,127]};if(!song||!Number.isInteger(index)||index<0||index>=song.events.length||!bounds[field]||!Number.isInteger(value)||value<bounds[field][0]||value>bounds[field][1])throw Error('Choose a supported song field and an in-range value.');const result=changes.filter(c=>!(c.kind==='note'&&c.song_id===songId&&c.index===index&&c.field===field));if(value!==song.events[index][field])result.push({kind:'note',song_id:songId,index,field,value});return result;}
export function restoreSoundChanges(doc,encoded){
 if(!doc)return [];const saved=JSON.parse(encoded);if(saved?.document_id!==doc.document_id)return [];
 if(!Array.isArray(saved.changes)||saved.changes.length>256)throw Error('Saved audio edits exceed the change budget.');
 let result=[];const seen=new Set();
 for(const c of saved.changes){
  if(!c||typeof c!=='object'||Array.isArray(c))throw Error('Saved audio edits contain an invalid change.');
  const key=JSON.stringify([c.kind,c.song_id??c.sample_id,c.index,c.field]);if(seen.has(key))throw Error('Saved audio edits contain duplicate changes.');seen.add(key);
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
