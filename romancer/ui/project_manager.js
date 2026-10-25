import {esc,button,read} from './common.js';

export function newProjectForm(name=''){
 return `<p>A separate workspace for your sources, builds and discoveries.</p><label class="field"><span>Project name</span><input id="new-project-name" value="${esc(name)}" maxlength="120" placeholder="My ROM project" required></label><div class="actions">${button('Create & import ROM','create-project-import',{primary:true,icon:'plus'})}${button('Create empty project','create-project')}</div>`;
}

export function projectActions(ctx){
 const {state}=ctx;
 const create=async withImport=>{const project=await ctx.api.call('project.create',{name:read('new-project-name').trim()});ctx.closeModal();await ctx.openProject(project.project_id);if(withImport)await ctx.importDialog();};
 const manager=async()=>{
  const [live,trash]=await Promise.all([ctx.api.call('projects.list',{}),ctx.api.call('projects.trash',{})]);state.projects=live.projects;
  ctx.modal('Projects',`<div class="actions">${button('New project','new-project',{primary:true,icon:'plus'})}</div>${live.projects.length?live.projects.map(p=>`<div class="resource-row"><div class="resource-meta"><strong>${esc(p.name)}</strong><small>${p.sources.length} sources · ${p.builds.length} builds</small></div><div class="actions">${button('Open','manager-open',{id:p.project_id})}${button('Delete project','manager-delete',{id:p.project_id})}</div></div>`).join(''):'<p>No projects yet.</p>'}<details><summary>Trash · ${trash.projects.length}</summary><p>Restore a deleted project with its sources and builds intact.</p>${trash.projects.map(p=>`<div class="resource-row"><strong class="resource-meta">${esc(p.name)}</strong>${button('Restore','manager-restore',{id:p.trash_id})}</div>`).join('')||'<p>Trash is empty.</p>'}</details>`);
 };
 return {
  'new-project':()=>ctx.modal('New project',newProjectForm(state.droppedImportFile?.name?.replace(/\.[^.]+$/,'')||'')),
  'create-project':()=>create(false),'create-project-import':()=>create(true),'projects-manage':manager,
  'manager-open':async node=>{ctx.closeModal();await ctx.openProject(node.dataset.id);},
  'manager-delete':async node=>{const result=await ctx.api.call('projects.list',{}),p=result.projects.find(p=>p.project_id===node.dataset.id);if(!p)throw Error('Project is no longer available.');ctx.modal('Delete project?',`<p>Move <strong>${esc(p.name)}</strong> and its project files to Trash?</p><p>Your original ROM files stay where they are. You can restore this project from Projects → Trash.</p><div class="actions">${button('Move to Trash','manager-delete-confirm',{id:p.project_id})}${button('Keep project','projects-manage',{primary:true})}</div>`);},
  'manager-delete-confirm':async node=>{await ctx.flushDrafts();if(state.project?.project_id===node.dataset.id)await ctx.closeProject();await ctx.api.call('project.delete',{project_id:node.dataset.id});await ctx.refreshProject();await ctx.render();await manager();ctx.notify('Project moved to Trash.');},
  'manager-restore':async node=>{await ctx.api.call('project.undelete',{trash_id:node.dataset.id});await ctx.refreshProject();await ctx.render();await manager();ctx.notify('Project restored.');}
 };
}
