import assert from 'node:assert/strict';
import {saveManager} from '../romancer/ui/save_manager.js';
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'},runtime:null};
const ctx={state,use:()=>{},draft:(_k,f)=>f};
const html=saveManager(ctx,{saves:[{save_id:'id',name:'<save>',size:4,origin:'imported',created_utc:''}]});
assert.ok(!html.includes('<save>'));assert.match(html,/Restart with selected save/);assert.match(html,/automatic backup/);assert.match(html,/Load the selected ROM/);assert.match(html,/data-action="save-export"/);
console.log('Save controls explain setup, expose private exports, and name the automatic restore backup.');
