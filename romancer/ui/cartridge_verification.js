import {esc,badge,button} from './common.js';
import {selectionKey} from './tool_inputs.js';

export const checkLabel=status=>({PASS:'Consistent',FAIL:'Mismatch',WARN:'Needs attention',NOT_CHECKED:'Not checked'})[status]||'Not checked';
export const checkTone=status=>({PASS:'good',FAIL:'danger',WARN:'warm'})[status]||'neutral';

export function registerVerificationNavigation(ctx){
 const scope=selectionKey(ctx.state);
 ctx.use({'rom-verification-view':async node=>{
  const {state}=ctx,health=state.romScans?.[scope]?.result?.health,offset=Number(node.dataset.id);
  if(scope!==selectionKey(state)||health?.source?.sha256!==state.artifact?.sha256||!Number.isSafeInteger(offset)||offset<0||offset>=state.artifact.size||
   !health.checks?.some(check=>check.locations?.some(location=>location.offset===offset)))throw Error('Scan the selected source again before opening verification bytes.');
  state.resourceJump=offset;await ctx.navigate('resources');
 }});
}

export function verificationResults(health){
 if(!health?.checks?.length)return '';
 const counts={};for(const check of health.checks)counts[check.status]=(counts[check.status]||0)+1;
 const summary=Object.entries(counts).map(([status,n])=>n+' '+checkLabel(status).toLowerCase()).join(' · ');
 return `<details class="cartridge-verification" ${counts.FAIL||counts.WARN?'open':''}><summary>Cartridge verification · ${esc(summary)}</summary><div class="table-wrap"><table><thead><tr><th>Check</th><th>Result</th><th>Details</th></tr></thead><tbody>${health.checks.map(check=>`<tr><td>${esc(check.name)}${Number.isSafeInteger(check.cpu_address)?`<br><code>CPU 0x${check.cpu_address.toString(16).toUpperCase()}</code>`:''}</td><td>${badge(checkLabel(check.status),checkTone(check.status))}</td><td>${esc(check.detail)}${(check.locations||[]).map(location=>button(location.label||'View bytes','rom-verification-view',{id:String(location.offset)})).join('')}</td></tr>`).join('')}</tbody></table></div><p>These are static cartridge checks. Revision matching and successful gameplay require separate evidence.</p></details>`;
}
