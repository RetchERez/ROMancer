// Update ready banner: shows a newer release, downloads and checks it, then closes, updates and reopens ROMancer.
// The banner lives outside #app so page renders never remove it. All network work is done by the local service.
import {esc} from './common.js';

const SLOW=30*60*1000,FAST=1000,RETRY_BUSY=5000;
const view={status:null,wanted:false,timer:0,applying:false};

function el(){
 let node=document.getElementById('update-banner');
 if(!node){node=document.createElement('div');node.id='update-banner';node.setAttribute('role','status');node.hidden=true;document.body.append(node);}
 return node;
}
const percent=p=>typeof p==='number'?` ${Math.floor(p*100)}%`:'';

export function bannerHtml(s,wanted){
 if(!s||!s.available||!s.latest)return '';
 const v=esc(s.latest.version),page=esc(s.latest.page||'');
 const notes=`<button type="button" data-update="notes">What’s new</button>`;
 if(!s.can_apply)return `<strong>Update ready: v${v}</strong><span>${esc(s.reason||'Download it from the release page.')}</span>${notes}<a href="${page}" target="_blank" rel="noopener">Release page</a><button type="button" data-update="hide" aria-label="Hide until next start">Later</button>`;
 if(s.task==='downloading')return `<strong>Downloading v${v}${percent(s.progress)}</strong><span>You can keep working, and ROMancer restarts when it's done.</span>`;
 if(s.task==='unpacking')return `<strong>Checking v${v}</strong><span>Every file is checked against the release before anything is changed.</span>`;
 if(s.task==='restarting')return `<strong>Restarting to update to v${v}</strong>`;
 if(wanted&&s.ready&&s.busy)return `<strong>v${v} is ready</strong><span>${esc(s.busy)} ROMancer restarts by itself as soon as it can.</span><button type="button" data-update="cancel">Not now</button>`;
 if(s.error)return `<strong>Update ready: v${v}</strong><span class="error">${esc(s.error)}</span><button type="button" data-update="go">Try again</button>${notes}`;
 return `<strong>Update ready: v${v}</strong>${notes}<button type="button" class="primary" data-update="go">Update and restart</button><button type="button" data-update="hide" aria-label="Hide until next start">Later</button>`;
}

function draw(){
 const node=el(),html=view.hidden?'':bannerHtml(view.status,view.wanted);
 node.innerHTML=html;node.hidden=!html;
}

function overlay(version){
 const node=document.createElement('div');node.id='update-overlay';node.setAttribute('role','alert');
 node.innerHTML=`<div><img src="/mark.svg" alt=""><h1>Updating ROMancer to v${esc(version)}</h1><p>ROMancer closes, updates and opens again by itself. Your projects are not touched.</p><p class="subtle">If this window stays open, you can close it.</p></div>`;
 document.body.append(node);
}

function notesDialog(s){
 const dialog=document.createElement('dialog');dialog.className='update-notes';
 dialog.innerHTML=`<div class="dialog-heading"><h2>What’s new in v${esc(s.latest.version)}</h2><button type="button" data-close aria-label="Close">×</button></div><pre>${esc(s.latest.notes||'No notes were published with this release.')}</pre><p><a href="${esc(s.latest.page)}" target="_blank" rel="noopener">Open the release page</a></p>`;
 dialog.addEventListener('click',event=>{if(event.target===dialog||event.target.closest('[data-close]'))dialog.close();});
 dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
}

export function startUpdates(api,notify){
 const schedule=ms=>{clearTimeout(view.timer);view.timer=setTimeout(poll,ms);};
 async function apply(){
  if(view.applying)return;view.applying=true;
  try{
   const result=await api.call('system.update_apply',{});
   if(result.restarting){overlay(result.version);setTimeout(()=>{try{window.close();}catch{}},4000);return;}
   view.status={...view.status,busy:result.busy||null,error:result.busy?'':result.error||''};draw();
   if(result.busy)schedule(RETRY_BUSY);
  }catch(error){view.status={...view.status,error:error.message};draw();}
  finally{view.applying=false;}
 }
 async function poll(){
  let s;try{s=await api.call('system.update_status',{});}catch{schedule(SLOW);return;}
  view.status=s;
  if(s.finished){notify(s.finished.updated?`ROMancer was updated to v${s.finished.to}.`:s.finished.message,!s.finished.updated);api.call('system.update_seen',{}).catch(()=>{});}
  draw();
  if(view.wanted&&s.ready&&!s.task){await apply();return;}
  schedule(s.task||(view.wanted&&!s.error)?FAST:SLOW);
 }
 el().addEventListener('click',async event=>{
  const action=event.target.closest('[data-update]')?.dataset.update;if(!action)return;
  if(action==='notes')notesDialog(view.status);
  else if(action==='hide'){view.hidden=true;draw();}
  else if(action==='cancel'){view.wanted=false;clearTimeout(view.timer);draw();schedule(SLOW);}
  else if(action==='go'){
   view.wanted=true;
   if(view.status?.ready){await apply();return;}
   try{view.status=await api.call('system.update_start',{});if(view.status.ok===false)throw Error(view.status.error);}catch(error){view.status={...view.status,error:error.message};}
   draw();schedule(FAST);
  }
 });
 poll();
 return {checkNow:async()=>{const s=await api.call('system.update_check',{});view.status=s;view.hidden=false;draw();schedule(FAST);return s;},status:()=>view.status};
}
