import assert from 'node:assert/strict';
import {LevelDraft,levelBrushPalette} from '../romancer/ui/level_canvas.js';
const doc={rooms:[],tiles:[Array(64).fill(0)],palette:[[0,0,0]],block_width:1,block_height:1,metatiles:Array.from({length:256},()=>[0])};const model=new LevelDraft(doc);
let html=levelBrushPalette(doc,model,143);assert.equal((html.match(/data-level-brush=/g)||[]).length,64);assert.ok(html.includes('data-level-brush="143" aria-pressed="true"'));assert.ok(!html.includes('data-level-brush="0" '));
html=levelBrushPalette(doc,model,143,0);assert.equal((html.match(/data-level-brush=/g)||[]).length,64);assert.ok(html.includes('data-level-brush="0" '));assert.ok(!html.includes('data-level-brush="143" '));assert.throws(()=>levelBrushPalette(doc,model,0,4),/bounds/);
const small={...doc,metatiles:[[0],[0]]};assert.equal((levelBrushPalette(small,new LevelDraft(small),0).match(/data-level-brush=/g)||[]).length,2);
console.log('Large terrain palettes stay at 64 visual brushes per page; selected and explicitly paged ranges remain reachable.');
