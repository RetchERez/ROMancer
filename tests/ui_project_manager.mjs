import assert from 'node:assert/strict';
import {projectActions,newProjectForm} from '../romancer/ui/project_manager.js';
let events=[],modal='';globalThis.document={getElementById:()=>({value:'New hack'})};
const ctx={state:{projects:[],project:null},api:{call:async(op,p)=>{events.push(op);if(op==='project.create')return {project_id:'new'};return {projects:[]};}},modal:(title,html)=>{modal=html;},closeModal(){},openProject:async id=>events.push('open:'+id),importDialog:async()=>events.push('import'),closeProject:async()=>{},flushDrafts:async()=>{},refreshProject:async()=>{},render:async()=>{},notify(){}};
const actions=projectActions(ctx);assert.match(newProjectForm(),/Project name/);assert.match(newProjectForm(),/Create empty project/);
await actions['create-project-import']();assert.deepEqual(events,['project.create','open:new','import'],'new work must get a separate project before importing');
events=[];await actions['projects-manage']();assert.ok(events.includes('projects.trash'));assert.match(modal,/Trash/);
console.log('New-project form creates a separate workspace before import; project manager exposes recovery.');
