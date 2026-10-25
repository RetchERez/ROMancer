import {esc,button} from './common.js';
import {selectionTicket,selectionCurrent} from './project_flow.js';

export function renderHub(data){
 const lessons=data?.lessons||[],progress=data?.progress||{};
 return `<p>Short, optional lessons. Checks mark finished lessons; skipped lessons stay unchecked.</p><div class="grid-even">${['Basic','Advanced'].map(section=>`<section class="card"><h2>${section}</h2>${lessons.filter(l=>l.section===section).map(lesson=>{const status=progress[lesson.id],done=status==='completed';return `<div class="lesson-row"><span class="lesson-check ${done?'complete':''}" aria-label="${done?'Completed':status==='skipped'?'Skipped':'Not started'}">${done?'✓':status==='skipped'?'–':'○'}</span><div class="resource-meta"><strong>${esc(lesson.title)}</strong><small>${lesson.steps.length} steps${status==='skipped'?' · Skipped':''}</small></div>${button(done?'Replay':'Start','tutorial-start',{id:lesson.id})}</div>`;}).join('')}</section>`).join('')}</div>`;
}

export function createTutorial(ctx){
 const {state}=ctx;state.tutorial=null;let busy=false,revision=0,lastHighlight='';
 const lesson=()=>state.tutorialData?.lessons.find(l=>l.id===state.tutorial?.lesson_id);
 async function dismissPrompt(openHub){
  const checked=document.getElementById('tutorial-never')?.checked===true;
  try{state.tutorialData=await ctx.api.call('tutorial.preferences',{never_ask_again:checked});}
  finally{ctx.closeModal();}
  if(openHub)await ctx.navigate('tutorials');
 }
 async function init(){
  try{
   state.tutorialData=await ctx.api.call('tutorial.get');
   if(state.tutorialData.prompt&&!document.getElementById('modal')?.open)ctx.modal('A quick tour?',`<p>Four short lessons. Start with Basic, or explore Advanced.</p><label class="tutorial-choice"><input type="checkbox" id="tutorial-never">Never ask again</label><div class="actions">${button('Start tutorial','tutorial-accept',{primary:true})}${button('Not now','tutorial-decline')}</div>`);
  }catch{ctx.notify('Tutorials are unavailable right now. Your workspace is ready.');}
 }
 async function start(id){
  if(busy)return;if(state.tutorial)throw Error('Finish or skip the current lesson first.');
  const selected=state.tutorialData?.lessons.find(l=>l.id===id);if(!selected)throw Error('Choose a lesson from Tutorials.');
  busy=true;const request=++revision,ticket=selectionTicket(state),previous=state.project?.project_id||null,previousArtifact=state.artifact?.artifact_id||null;
  try{
   const practice=await ctx.api.call('tutorial.practice');
   if(request!==revision||!selectionCurrent(state,ticket))return;
   await ctx.openProject(practice.project_id);
   if(request!==revision||state.project?.project_id!==practice.project_id)return;
   state.tutorial={lesson_id:id,step:0,visited:[0],practice:practice.project_id,previous,previousArtifact,minimized:false};lastHighlight='';
   await ctx.navigate(selected.steps[0].page);
  }finally{busy=false;}
 }
 async function move(direction){
  const active=state.tutorial,current=lesson();if(!active||!current||busy)return;
  if(state.project?.project_id!==active.practice||state.page!==current.steps[active.step].page)return resume();
  const next=active.step+direction;if(next<0||next>=current.steps.length)return;
  active.step=next;if(!active.visited.includes(next))active.visited.push(next);
  await ctx.navigate(current.steps[next].page);
 }
 async function end(outcome){
  const active=state.tutorial,current=lesson();if(!active||!current||busy)return;
  if(outcome==='completed'&&(active.step!==current.steps.length-1||active.visited.length!==current.steps.length))throw Error('Reach the last step before finishing this lesson.');
  busy=true;const request=revision,ticket=state.selectionRevision;
  try{
   const result=await ctx.api.call('tutorial.progress',{lesson_id:active.lesson_id,outcome});
   if(request!==revision||state.tutorial!==active)return;
   state.tutorialData=result;state.tutorial=null;revision++;
   if(!selectionCurrent(state,ticket)){await ctx.render();return;}
   if(state.project?.project_id===active.practice&&active.previous&&active.previous!==active.practice){
    const restore=ctx.openProject(active.previous),restoreTicket=state.selectionRevision;await restore;
    if(!selectionCurrent(state,restoreTicket)){await ctx.render();return;}
    if(active.previousArtifact&&state.artifact?.artifact_id!==active.previousArtifact)await ctx.setArtifact(active.previousArtifact);
    if(!selectionCurrent(state,restoreTicket)){await ctx.render();return;}
   }else if(state.project?.project_id===active.practice&&!active.previous){
    await ctx.closeProject();
   }
   await ctx.navigate('tutorials');
  }finally{busy=false;}
 }
 async function resume(){
  const active=state.tutorial,current=lesson();if(!active||!current||busy)return;
  if(state.project?.project_id!==active.practice)await ctx.openProject(active.practice);
  if(state.tutorial!==active||state.project?.project_id!==active.practice)return;
  active.minimized=false;await ctx.navigate(current.steps[active.step].page);
 }
 async function openHub(){if(state.tutorial)await end('skipped');else await ctx.navigate('tutorials');}
 function bind(){ctx.use({
  'tutorial-hub':openHub,'tutorial-accept':()=>dismissPrompt(true),'tutorial-decline':()=>dismissPrompt(false),
  'tutorial-start':node=>start(node.dataset.id),'tutorial-next':()=>move(1),'tutorial-back':()=>move(-1),
  'tutorial-finish':()=>end('completed'),'tutorial-skip':()=>end('skipped'),'tutorial-resume':resume,
  'tutorial-toggle':async()=>{if(state.tutorial){state.tutorial.minimized=!state.tutorial.minimized;await ctx.render();}}
 });}
 function panel(){
  const active=state.tutorial,current=lesson();if(!active||!current||active.minimized)return '';
  const step=current.steps[active.step],paused=state.project?.project_id!==active.practice||state.page!==step.page;
  return `<aside class="tutorial-panel" aria-label="Guided tutorial"><div class="card-heading"><strong>${esc(current.title)}</strong>${button('Minimize','tutorial-toggle')}</div><p class="subtle">Step ${active.step+1} of ${current.steps.length}</p><h2 id="tutorial-title" tabindex="-1">${esc(paused?'Lesson paused':step.title)}</h2><p>${esc(paused?'Resume to return to the practice workshop.':step.body)}</p><div class="actions">${paused?button('Resume lesson','tutorial-resume',{primary:true}):`${button('Back','tutorial-back',{disabled:active.step===0})}${active.step===current.steps.length-1?button('Finish lesson','tutorial-finish',{primary:true}):button('Next','tutorial-next',{primary:true})}`}${button('Skip lesson','tutorial-skip')}</div></aside>`;
 }
 function mount(){
  const active=state.tutorial,current=lesson();document.documentElement.classList.toggle('tutorial-running',!!active&&!active.minimized);
  document.querySelectorAll('.tutorial-target').forEach(node=>node.classList.remove('tutorial-target'));
  if(!active||!current||active.minimized||state.project?.project_id!==active.practice||state.page!==current.steps[active.step].page)return;
  const step=current.steps[active.step],target=document.querySelector(step.target)||document.querySelector('#main .page-heading');
  if(target){const detail=target.closest('details');if(detail)detail.open=true;target.classList.add('tutorial-target');
   const key=active.lesson_id+':'+active.step;if(key!==lastHighlight){lastHighlight=key;target.scrollIntoView({block:'center'});document.getElementById('tutorial-title')?.focus({preventScroll:true});}}
 }
 return {init,bind,panel,mount,dismissPrompt};
}
