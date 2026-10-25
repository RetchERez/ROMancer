import assert from 'node:assert/strict';
import {createTutorial,renderHub} from '../romancer/ui/tutorial.js';

const lessons=[['basic','Basic'],['advanced','Advanced']].map(([id,section])=>({id,section,title:section+' lesson',steps:[0,1,2].map(i=>({page:['overview','assets','help'][i],target:'#main',title:'Step '+i,body:'One short instruction.'}))}));
function fixture(){
 const progress={},calls=[],handlers={},state={project:{project_id:'user'},artifact:{artifact_id:'edited-build'},page:'overview',results:{},selectionRevision:0};let checked=false,practice;
 globalThis.document={getElementById:id=>id==='tutorial-never'?{checked}:id==='modal'?{open:false,close(){}}:null};
 const status=()=>({ok:true,prompt:true,never_ask_again:false,progress,lessons});
 const ctx={state,use:h=>Object.assign(handlers,h),notify(){},modal:(title,body)=>{ctx.prompt={title,body};},closeModal(){},render:async()=>{},
  navigate:async page=>{state.page=page;calls.push(['navigate',page]);},
  openProject:async id=>{state.selectionRevision++;state.project={project_id:id};state.artifact={artifact_id:'user-original'};},setArtifact:async id=>{state.artifact={artifact_id:id};},closeProject:async()=>{state.project=null;state.artifact=null;state.selectionRevision++;},
  api:{call:async(op,p={})=>{calls.push([op,p]);if(op==='tutorial.get')return status();if(op==='tutorial.practice')return practice?await practice:{project_id:'practice'};
   if(op==='tutorial.progress'){if(progress[p.lesson_id]!=='completed')progress[p.lesson_id]=p.outcome;return status();}if(op==='tutorial.preferences')return {...status(),never_ask_again:p.never_ask_again};throw Error(op);}}};
 const controller=createTutorial(ctx);controller.bind();return {ctx,state,handlers,controller,calls,progress,setChecked:v=>checked=v,setPractice:p=>practice=p};
}

{
 const f=fixture();await f.controller.init();assert.match(f.ctx.prompt.body,/Never ask again/);f.setChecked(true);await f.handlers['tutorial-decline']();
 assert.equal(f.calls.find(c=>c[0]==='tutorial.preferences')[1].never_ask_again,true);assert.equal(f.calls.some(c=>c[0]==='tutorial.practice'),false);assert.equal(f.state.project.project_id,'user');
}
{
 const f=fixture();await f.controller.init();await f.handlers['tutorial-start']({dataset:{id:'basic'}});
 await assert.rejects(f.handlers['tutorial-finish'](),/last step/);
 await f.handlers['tutorial-next']();await f.handlers['tutorial-next']();await f.handlers['tutorial-finish']();
 assert.equal(f.progress.basic,'completed');assert.equal(f.state.project.project_id,'user');assert.equal(f.state.page,'tutorials');assert.equal(f.state.artifact.artifact_id,'edited-build');
 await f.handlers['tutorial-start']({dataset:{id:'advanced'}});await f.handlers['tutorial-skip']();assert.equal(f.progress.advanced,'skipped');
 const hub=renderHub({...f.ctx.state.tutorialData,lessons,progress:f.progress});assert.match(hub,/>Basic</);assert.match(hub,/>Advanced</);assert.equal((hub.match(/aria-label="Completed"/g)||[]).length,1);assert.match(hub,/Skipped/);
}
{
 const f=fixture();await f.controller.init();let resolve;f.setPractice(new Promise(r=>resolve=r));const pending=f.handlers['tutorial-start']({dataset:{id:'basic'}});
 f.state.selectionRevision++;f.state.project={project_id:'new-choice'};resolve({project_id:'practice'});await pending;
 assert.equal(f.state.project.project_id,'new-choice');assert.equal(f.state.tutorial,null);
}
console.log('Optional prompt, durable checkbox, sequential completion, skipped checks and late-start selection guards passed.');
{
 const f=fixture();f.state.project=null;f.state.artifact=null;await f.controller.init();await f.handlers['tutorial-start']({dataset:{id:'basic'}});await f.handlers['tutorial-skip']();assert.equal(f.state.project,null);
}
