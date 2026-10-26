'use strict';

function romancerGuideMatches(documents,query,limit=12){
 const words=String(query).toLocaleLowerCase().trim().split(/\s+/).filter(Boolean).slice(0,20);
 if(!words.length)return [];
 return documents.map((doc,index)=>{
  const title=doc.title.toLocaleLowerCase(),aliases=(doc.aliases||'').toLocaleLowerCase(),text=doc.text.toLocaleLowerCase();
  const score=words.every(word=>(title+' '+aliases+' '+text).includes(word))?words.reduce((n,word)=>n+(title.includes(word)?10:aliases.includes(word)?5:1),0):0;
  return {doc,index,score};
 }).filter(row=>row.score).sort((a,b)=>b.score-a.score||a.index-b.index).slice(0,limit).map(row=>row.doc);
}

if(typeof document!=='undefined'){
 const input=document.getElementById('guide-query'),results=document.getElementById('guide-results'),status=document.getElementById('guide-search-status');
 if(input&&results&&status){
  const documents=[...document.querySelectorAll('section.chapter:not(#glossary):not(#index), .term')].map(node=>({id:node.id,title:node.querySelector('h2,dt')?.textContent||node.id,text:(node.innerText||node.textContent).replace(/\s+/g,' ').trim(),aliases:''}));
  const byId=new Map(documents.map(row=>[row.id,row]));
  for(const entry of document.querySelectorAll('.index-list li'))for(const link of entry.querySelectorAll('a[href^="#"]')){const row=byId.get(link.getAttribute('href').slice(1));if(row)row.aliases+=' '+(entry.querySelector('strong')?.textContent||'');}
  let timer;
  const search=()=>{
   const query=input.value.trim();results.replaceChildren();status.textContent='';if(!query)return;
   const matches=romancerGuideMatches(documents,query,13);
   status.textContent=matches.length?matches.length>12?'Showing the first 12 matches. Add a word to narrow the results.':matches.length+' matching topic'+(matches.length===1?'':'s')+'.':'No matching topics. Try a shorter term, or use the glossary below.';
   for(const row of matches.slice(0,12)){
    const item=document.createElement('li'),link=document.createElement('a'),snippet=document.createElement('p');link.href='#'+row.id;link.textContent=row.title;
    const word=query.toLocaleLowerCase().split(/\s+/)[0],position=row.text.toLocaleLowerCase().indexOf(word),start=Math.max(0,position-45);
    snippet.textContent=(start?'…':'')+row.text.slice(start,start+170)+(row.text.length>start+170?'…':'');item.append(link,snippet);results.append(item);
   }
  };
  input.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(search,120);});
  document.getElementById('guide-search-form')?.addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);search();});
  document.getElementById('guide-search-clear')?.addEventListener('click',()=>{clearTimeout(timer);input.value='';search();input.focus();});
 }
}
