import {esc,field,select,read,button} from './common.js';
import {selectionKey} from './tool_inputs.js';

export function hardwareReference(ctx){
 const {state}=ctx;if(!state.artifact)return '';
 const scope=selectionKey(state),system=state.artifact.system_id;
 const doc=state.romScans?.[scope]?.result?.hardware_reference;
 const result=state.hardwareAddress?.scope===scope?state.hardwareAddress.result:null;
 ctx.use({'hardware-explain':async()=>{
  if(scope!==selectionKey(state))throw Error('The selected source changed. Explain the current address again.');
  const generation=state.hardwareRequestGeneration=(state.hardwareRequestGeneration||0)+1;
  const result=await ctx.api.call('systems.classify_address',{system_id:system,address:Number(read('hardware-address')),domain:read('hardware-domain')});
  if(scope!==selectionKey(state)||state.hardwareRequestGeneration!==generation)return;
  state.hardwareAddress={scope,result};await ctx.render();
 }});
 const domains=Object.keys(doc?.domains||{cpu:0});
 return `<details class="card hardware-reference"><summary>Hardware & address help</summary>${doc?`<p><strong>${esc(doc.cpu)}</strong> · ${esc(doc.endian)}-endian CPU convention</p><p>${esc(doc.mapping)}</p><p>${esc(doc.graphics)}</p>`:'<p>Finish a ROM scan for the system overview. Address help is available now.</p>'}<div class="field-row">${select('hardware-domain','Address domain',domains.map(domain=>[domain,({cpu:'CPU address',ppu:'NES PPU address',vram:'Physical VRAM offset',apu:'SNES audio CPU address'})[domain]||domain]),ctx.draft('hardware-domain','cpu'))}${field('hardware-address','Address or offset',ctx.draft('hardware-address','0x8000'))}${button('Explain address','hardware-explain')}</div>${result?.ok?`<div class="notice"><strong>${esc(result.label)}</strong><p>${esc(result.note)}</p><p>This describes a hardware range. It does not identify a game value or resolve a ROM file offset.</p></div>`:''}<p>For file bytes, use Address explorer with a checked mapping. Native memory snapshots use offsets within the core’s exposed region.</p>${doc?`<details><summary>Technical references</summary>${doc.references.filter(url=>/^https?:\/\//i.test(url)).map((url,index)=>`<p><a href="${esc(url)}" target="_blank" rel="noreferrer noopener">Reference ${index+1}</a></p>`).join('')}</details>`:''}</details>`;
}
