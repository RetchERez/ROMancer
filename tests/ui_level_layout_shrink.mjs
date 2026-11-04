import assert from 'node:assert/strict';
import {render} from '../romancer/ui/views/levels.js';
const doc={ok:true,document_id:'small',source_sha256:'sha',uses:{},tiles:[Array(64).fill(0)],palette:[[0,0,0]],block_width:1,block_height:1,metatiles:[[0],[0]],definition:{rooms:[{id:'r',objects:null}]},rooms:[{id:'r',name:'R',width:1,height:1,terrain:[0],collision:null,objects:[]}]};
for(const drafts of [{'level-brush-page':'3'},{'level-brush':'99999'},{'level-brush-page':'bad'}]){const ctx={state:{project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha',system_id:'nes'},results:{'levels.inspect':doc}},draft:(k,d)=>drafts[k]??d,setDraft:(k,v)=>drafts[k]=v,use(){}};assert.match(await render(ctx),/Room editor/);}
console.log('Stale and malformed terrain brush pages cannot hide a smaller checked layout.');
