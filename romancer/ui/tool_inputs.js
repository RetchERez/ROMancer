import {esc} from './common.js';
export const selectionKey=state=>[state.project?.project_id,state.artifact?.artifact_id,state.artifact?.sha256].join(':')+(state.selectionRevision===undefined?'':':'+state.selectionRevision);
export function fileInput(id,label,accept){return `<label class="field"><span>${esc(label)}</span><input type="file" id="${id}" accept="${accept}"></label>`;}
export function downloadDocument(document,name,type='application/json'){
 const blob=new Blob([typeof document==='string'?document:JSON.stringify(document,null,2)],{type}),url=URL.createObjectURL(blob),link=window.document.createElement('a');
 link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
}

export async function readJsonFile(id,maxBytes){
 const file=document.getElementById(id)?.files?.[0];
 if(!file)throw Error('Choose a JSON file first.');
 if(!file.size||file.size>maxBytes)throw Error('This JSON file is outside the supported size.');
 try{return JSON.parse(await file.text());}catch{throw Error('Choose a valid ROMancer JSON file.');}
}
