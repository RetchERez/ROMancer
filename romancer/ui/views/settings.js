import {supportControls} from '../project_checks.js';
import {readPreference,writePreference,removePreference} from '../preferences.js';
import {applyInterfaceScale} from '../interface_scale.js';
import {esc,button,badge,field,read,heading,report,select} from '../common.js';
const columns=[['identification','Identification'],['raw_inspection','Inspection'],['structured_formats','Declared formats'],['automatic_resource_discovery','Resource discovery'],['runtime_control','Saved setup']];
export async function render(ctx){
 const c=ctx.state.capabilities,packs=[...(c.systems?.systems||[])].sort((a,b)=>Number(b.release_focus)-Number(a.release_focus));
 const setups=Object.fromEntries(await Promise.all(packs.map(async pack=>{
  try{const saved=await ctx.api.call('profiles.get',{system_id:pack.id});
   if(!saved.profile)return [pack.id,{status:'Choose core',tone:'neutral',reason:'No core is configured in this workspace.'}];
   await ctx.api.call('profiles.validate',{system_id:pack.id});
   return [pack.id,{status:'Ready',tone:'good',reason:'Core and system-file identities checked. Gameplay needs a loaded ROM.'}];
  }catch(error){return [pack.id,{status:'Needs attention',tone:'warm',reason:error.message}];}
 })));
 ctx.use({'settings-setup':async node=>{const family=node.dataset.id;
  if(!ctx.state.project){const project=await ctx.api.call('project.demo_system',{system_id:family});await ctx.openProject(project.project_id);}
  ctx.state.profileFamily=family;ctx.state.profileLoadedFamily=null;await ctx.navigate('playtest');
 }});
 ctx.use({'interface-scale':()=>{const scale=applyInterfaceScale(read('interface-scale'));writePreference('romancer-scale',String(scale));ctx.notify('Interface size saved.');},'project-backup':()=>ctx.run('project.backup',{...ctx.projectParams(),destination:read('backup-path'),roles:['sources','builds','reports','sessions','captures']}),'project-restore':async()=>{const result=await ctx.run('project.restore',{archive:read('restore-path')},{render:false});await ctx.refreshProject();ctx.notify('Project restored. Select it in the project list.');await ctx.render();},'project-migrate':()=>ctx.run('project.migrate',ctx.projectParams()),'project-recover':()=>ctx.run('project.recover_lock',ctx.projectParams())});
 return `${heading('Settings & capabilities','Settings','System formats, configured tools, and measured evidence are reported separately.')}
 ${supportControls(ctx)}<section class="card"><h3>Getting started</h3><p>Basic and Advanced lessons, at your pace.</p>${button('Open tutorials','tutorial-hub')}</section><section class="card"><h3>Appearance</h3>${select('interface-scale','Interface size',[[100,'100%'],[125,'125%'],[150,'150%'],[200,'200%']],readPreference('romancer-scale')||100)}${button('Apply size','interface-scale')}</section><section class="card"><h3>Projects & recovery</h3>${ctx.state.project?`${field('backup-path','Private backup file',ctx.draft('backup-path',ctx.state.project.path+'-backup.zip'))}<p class="subtle">Includes source images, builds, saves, captures and reports.</p><div class="actions">${button('Save private backup','project-backup')}${button('Migrate project','project-migrate')}${button('Recover abandoned lock','project-recover')}</div>`:''}${field('restore-path','Backup to restore','',{placeholder:'C:\\Backups\\project.zip'})}${button('Restore project','project-restore')}</section><div class="grid-even"><section class="card"><h3>Application</h3><div class="table-wrap"><table><tbody>
 <tr><td>Version</td><td>${esc(c.display_version||c.version)}</td></tr><tr><td>Runtime</td><td>Python ${esc(c.python)}</td></tr><tr><td>Platform</td><td>${esc(c.platform)}</td></tr>
 <tr><td>Image support</td><td>${badge(c.pillow?'Pillow available':'Pillow missing',c.pillow?'good':'warm')}</td></tr><tr><td>Project storage</td><td>Owned source copies and separate builds</td></tr>
 <tr><td>Server</td><td>Authenticated loopback session</td></tr></tbody></table></div><div class="notice">${esc(c.runtime_note)}</div></section>
 <section class="card"><h3>Systems</h3><p>NES · SNES · GEN · Game Boy · GBA</p><p class="subtle">Declare text and graphics for your source. Select a saved core setup to playtest.</p>${button('About & credit','about',{icon:'shield'})}</section></div>
 <section class="card"><h3>System support matrix</h3><div class="table-wrap"><table><thead><tr><th>Family</th>${columns.map(([,label])=>`<th>${label}</th>`).join('')}</tr></thead><tbody>
 ${packs.map(pack=>`<tr><td><strong>${esc(pack.label)}${pack.release_focus?'':' (advanced)'}</strong><br><small>${esc(pack.formats.join(', '))}</small></td>${columns.map(([key])=>{const capability=key==='runtime_control'?setups[pack.id]:pack.capabilities[key];const label=capability.status==='supported'?'Available':capability.status==='experimental'?'Header-based':capability.status;return `<td title="${esc(capability.reason)}">${badge(label,capability.tone||(capability.status==='supported'?'good':'neutral'))}${key==='runtime_control'?`<div class="actions">${button(capability.status==='Ready'?'Open setup':'Set up','settings-setup',{id:pack.id})}</div>`:''}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>
 <details><summary>What these statuses mean</summary><p>Available describes the listed editing feature. Header-based identification, including SNES, can remain ambiguous. Ready means saved core inputs were checked; it does not certify every game.</p><p>Choose core is a setup step for this workspace. Open Set up to find a local core. ROM health checks live in Resources.</p></details></section>
 ${report(c.systems,'Current system registry')}`;
}
