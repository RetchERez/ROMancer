// Bounded local playback of the worker's measured stereo PCM.
export function decodePCM(packet){
 if(packet?.format!=='s16le'||packet.channels!==2||packet.complete!==true||packet.dropped_frames||packet.invalid_batches||!Number.isFinite(packet.sample_rate)||packet.sample_rate<8000||packet.sample_rate>192000||!Number.isSafeInteger(packet.captured_frames)||packet.captured_frames<0||packet.captured_frames>48000)throw new Error('Audio packet is incomplete or outside playback limits.');
 const encoded=packet.pcm_s16le_base64;if(typeof encoded!=='string'||encoded.length>256000||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded))throw new Error('Invalid PCM encoding.');
 const raw=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));if(raw.length!==packet.captured_frames*4)throw new Error('Audio sample count differs from the packet.');
 const view=new DataView(raw.buffer),left=new Float32Array(packet.captured_frames),right=new Float32Array(packet.captured_frames);
 for(let i=0;i<left.length;i++){left[i]=view.getInt16(i*4,true)/32768;right[i]=view.getInt16(i*4+2,true)/32768;}
 return {left,right,rate:packet.sample_rate,duration:left.length/packet.sample_rate};
}
export function soundCheckPacket(){const count=1000,raw=new Uint8Array(count*4),view=new DataView(raw.buffer);for(let i=0;i<count;i++){const sample=Math.round(Math.sin(i*2*Math.PI*440/8000)*6000);view.setInt16(i*4,sample,true);view.setInt16(i*4+2,sample,true);}return {format:'s16le',channels:2,sample_rate:8000,captured_frames:count,complete:true,dropped_frames:0,invalid_batches:0,pcm_s16le_base64:btoa(String.fromCharCode(...raw))};}
export class LiveAudio{
 constructor(factory=()=>new AudioContext()){this.factory=factory;this.ticket=0;this.nodes=new Set();this.volume=1;this.muted=false;this.active=false;}
 async start(){this.stop();const ticket=this.ticket;try{this.context=this.factory();this.gain=this.context.createGain();this.gain.connect(this.context.destination);this.setVolume(this.volume,this.muted);await this.context.resume();if(ticket!==this.ticket)return;this.active=true;this.next=this.context.currentTime;}catch(error){if(ticket===this.ticket)this.stop();throw error;}}
 get queuedSeconds(){return this.active?Math.max(0,this.next-this.context.currentTime):0;}
 setVolume(value,muted=this.muted){if(!Number.isFinite(value)||value<0||value>1)throw new Error('Volume must be between 0 and 1.');this.volume=value;this.muted=muted;if(this.gain)this.gain.gain.value=muted?0:value;}
 enqueue(packet,ticket){if(!this.active||ticket!==this.ticket)return false;const decoded=decodePCM(packet);if(!decoded.left.length)return false;if(decoded.duration>.25)throw new Error('Audio packet exceeds 250 ms.');
  // Drop a late packet rather than scheduling an unbounded backlog.
  const start=Math.max(this.context.currentTime+.01,this.next);if(start+decoded.duration-this.context.currentTime>.25)return false;
  const buffer=this.context.createBuffer(2,decoded.left.length,decoded.rate);buffer.copyToChannel(decoded.left,0);buffer.copyToChannel(decoded.right,1);
  const node=this.context.createBufferSource();node.buffer=buffer;node.connect(this.gain);this.nodes.add(node);node.onended=()=>{this.nodes.delete(node);node.disconnect();};node.start(start);this.next=start+decoded.duration;return true;
 }
 stop(){this.ticket++;this.active=false;for(const node of this.nodes){try{node.stop();node.disconnect();}catch{}}this.nodes.clear();if(this.gain){this.gain.disconnect();this.gain=null;}if(this.context){this.context.close().catch(()=>{});this.context=null;}this.next=0;}
}
