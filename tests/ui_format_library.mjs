import assert from 'node:assert/strict';
import {formatLibrary,parseGuardRanges} from '../romancer/ui/format_library.js';
assert.deepEqual(parseGuardRanges('0x100 32\n512,16'),[{offset:256,length:32},{offset:512,length:16}]);
assert.throws(()=>parseGuardRanges('32 nope'));assert.throws(()=>parseGuardRanges('12 2'));
const actions={},state={page:'resources',project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'sha'},results:{}},nodes={};
globalThis.document={getElementById:id=>nodes[id]};globalThis.confirm=()=>true;
let calls=[];
const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:'a'}),projectParams:()=>({project_id:'p'}),draft:(k,d)=>d,use:r=>Object.assign(actions,r),render:async()=>{},refreshProject:async()=>{},notify:()=>{},
 api:{call:async()=>({ok:true,packs:[{pack_id:'pack',name:'<Source layout>',valid:true,mode:'exact',kinds:['tables']}]})},
 run:async(op,p)=>{calls.push([op,p]);return {ok:true,matched:true,exact_source:false,pack_id:'pack',review_id:'review',definitions:['tables'],replacements:[],rom_modified:false};}};
assert.match(await formatLibrary(ctx),/&lt;Source layout&gt;/);await actions['format-preview']({dataset:{id:'pack'}});await formatLibrary(ctx);
await assert.rejects(actions['format-apply'](),/guarded|Acknowledge/i);assert.equal(calls.filter(c=>c[0]==='formats.apply').length,0);
nodes['format-guarded-accept']={checked:true};await actions['format-apply']();assert.equal(calls.at(-1)[0],'formats.apply');assert.equal(calls.at(-1)[1].accept_guarded,true);
let resolve;ctx.api.call=()=>new Promise(r=>resolve=r);const pending=formatLibrary(ctx);state.page='debug';resolve({ok:true,packs:[]});assert.equal(await pending,'');
console.log('Format library bounds guard forms, escapes labels, requires compatibility acknowledgement and ignores late page results.');
