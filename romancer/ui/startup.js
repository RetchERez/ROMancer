// One local classic bundle avoids module-graph loading failures in desktop hosts.
(()=>{
 const original=location.href,launch=new URL(original).searchParams.get('launch');let ready=false;
 function recover(message){
  if(ready)return;
  const root=document.getElementById('app');if(!root)return;
  root.dataset.startupRecovered='true';
  const box=document.createElement('div');box.className='boot boot-recovery';
  const title=document.createElement('h1');title.textContent='ROMancer could not finish opening';
  const text=document.createElement('p');text.textContent='Try again, or reopen ROMancer from its desktop shortcut.';
  const actions=document.createElement('div');actions.className='actions';
  const retry=document.createElement('button');retry.textContent='Try again';retry.onclick=()=>location.reload();
  const browser=document.createElement('a');browser.textContent='Open in browser';browser.href=original;browser.target='_blank';browser.rel='noopener';
  const details=document.createElement('details'),summary=document.createElement('summary'),reason=document.createElement('pre');
  summary.textContent='Startup details';reason.textContent=String(message||'Startup took too long.').replace(/(#token=)[^\s]+/g,'$1[hidden]').slice(0,1200);
  details.append(summary,reason);actions.append(retry,browser);box.append(title,text,actions,details);root.replaceChildren(box);
 }
 const timer=setTimeout(()=>recover('The workbench did not finish opening within15 seconds.'),15000);
 window.addEventListener('error',event=>{if(!ready)recover(event.message||'A required application file could not load.');});
 window.addEventListener('unhandledrejection',event=>{if(!ready)recover(event.reason?.message||'Startup failed.');});
 window.addEventListener('romancer-ready',async()=>{
  if(document.getElementById('app')?.dataset.startupRecovered==='true')return;
  ready=true;clearTimeout(timer);
  if(launch&&/^[a-f0-9]{32}$/.test(launch)){try{
   let token=new URLSearchParams(new URL(original).hash.slice(1)).get('token');
   if(!token){try{token=sessionStorage.getItem('romancer-session');}catch{}}
   await fetch('/api/call',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(token||'')},body:JSON.stringify({operation:'system.ui_ready',parameters:{launch_id:launch}})});
  }catch{/* The launcher retains its browser fallback. */}}
 });
 window.addEventListener('romancer-startup-error',()=>recover('The local workspace could not be opened.'));
 const script=document.createElement('script');script.src='/app.bundle.js';script.onerror=()=>recover('The application bundle could not load. Reopen ROMancer from its launcher.');document.head.append(script);
})();
