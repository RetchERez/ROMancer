import assert from 'node:assert/strict';
import {buildHistory} from '../romancer/ui/build_history.js';
const state={project:{project_id:'p'},artifact:{artifact_id:'b'}};
const ctx={state,use:()=>{},draft:(_k,f)=>f};
const timeline={project_id:'p',artifacts:[{artifact_id:'a',name:'Original',kind:'source',sha256:'abc',size:3,parent_id:null,notes:''},{artifact_id:'b',name:'<unsafe>',kind:'build',sha256:'def',size:3,parent_id:'a',notes:'Title screen passed'}]};
const html=buildHistory(ctx,timeline);assert.match(html,/From Original/);assert.match(html,/Title screen passed/);assert.match(html,/data-action="history-select"/);assert.ok(!html.includes('<unsafe>'));assert.match(html,/Compare files/);
console.log('Build history shows actual parentage, selection and escaped notes.');
