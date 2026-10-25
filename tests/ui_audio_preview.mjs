import assert from 'node:assert/strict';
const {mountAudio,disposeAudio}=await import('../romancer/ui/runtime_setup.js');
const calls=[],audio={pause:()=>calls.push('pause'),removeAttribute:name=>calls.push(name),load:()=>calls.push('load')};
const context={fillRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){}},canvas={width:4,height:4,getContext:()=>context};
globalThis.document={getElementById:id=>id==='pcm-player'?audio:id==='pcm-wave'?canvas:null};
URL.createObjectURL=()=> 'blob:owned-pcm';URL.revokeObjectURL=url=>calls.push(url);
mountAudio({observed:true,sample_rate:8000,pcm_s16le_base64:Buffer.alloc(16).toString('base64')});
assert.equal(audio.src,'blob:owned-pcm');disposeAudio();disposeAudio();assert.deepEqual(calls,['pause','src','load','blob:owned-pcm']);
console.log('The native PCM preview releases its audio element and owned URL on disposal.');
