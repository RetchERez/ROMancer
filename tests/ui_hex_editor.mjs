import assert from 'node:assert/strict';
import {HexDraft,hexEditor} from '../romancer/ui/hex_editor.js';
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s',size:3},results:{},drafts:{}};
const data={artifact_id:'a',sha256:'s',offset:0,hex:'616263',length:3};
const draft=new HexDraft(state,data);draft.set(1,'58');assert.deepEqual(draft.edits(state),[{offset:1,before:'62',after:'58'}]);
draft.set(1,'62');assert.deepEqual(draft.edits(state),[]);
assert.throws(()=>draft.set(1,'xxx'),/two/i);assert.throws(()=>draft.set(9,'ff'),/visible/i);

const paged=new HexDraft(state,{...data,hex:'00'.repeat(256),length:256});paged.set(2,'7f');
for(let page=1;page<=1000;page++)paged.load({...data,offset:page*256,hex:'11'.repeat(256),length:256});
assert.ok(paged.original.size<=257,'Browsing pages must retain only visible bytes and staged originals.');
assert.deepEqual(paged.edits(state),[{offset:2,before:'00',after:'7f'}],'Paged-out edits still require their exact original byte.');
assert.throws(()=>paged.set(400,'ff'),/visible/i);
draft.set(2,'00');state.artifact={...state.artifact,sha256:'new'};assert.throws(()=>draft.edits(state),/selection/i);
state.artifact={...state.artifact,sha256:'s'};
const ctx={state,use:()=>{},draft:(_k,f)=>f};const html=hexEditor(ctx,data);
assert.match(html,/data-hex-offset="1"/);assert.match(html,/Review byte edits/);assert.match(html,/bookmarks/i);
const current=state.hexDraft;assert.throws(()=>hexEditor(ctx,{...data,artifact_id:'other'}),/selected|selection/i);assert.equal(state.hexDraft,current);assert.throws(()=>hexEditor(ctx,{...data,sha256:'other'}),/selected|selection/i);
console.log('Hex drafts preserve exact old bytes, reject invalid cells, and cannot cross source changes.');
