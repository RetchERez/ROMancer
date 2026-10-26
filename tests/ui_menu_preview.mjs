import assert from 'node:assert/strict';
import * as scripts from '../romancer/ui/views/scripts.js';

// Original synthetic MSB-row-packed glyphs: A is a bar, B a corner, C uses bit 8.
const glyph=(id,raw,width,advance,bearing={x:0,y:0})=>({id,bitmap:{offset:0,width,height:2,row_stride:Math.ceil(width/8),raw_hex:raw},bearing,advance_pixels:advance,ink_bounds:null});
const glyphs=[glyph('a','8080',2,3),glyph('b','c040',2,2,{x:-1,y:1}),glyph('gap','0000',2,2),glyph('c','00800080',9,9)];
const mapping=[{scalar:'A',glyph_id:'a'},{scalar:'B',glyph_id:'b'},{scalar:' ',glyph_id:'gap'},{scalar:'C',glyph_id:'c'}];
const record={id:'name',offset:0,capacity:8,used_bytes:4,padding_bytes:4,raw_hex:'41204200ffffffff',segments:[{index:0,text:'A B',length:3}],tokens:[{kind:'text'},{kind:'terminator'},{kind:'padding'}],read_only_reasons:[]};
const doc={ok:true,write_supported:true,document_id:'doc',source_sha256:'sha',schema_sha256:'script-schema',records:[record],encoding_glyphs:['A','B','C',' ']};
const placements=x=>[{glyph_id:'a',scalar:'A',scalar_index:0,x,y:1,advance_px:3},{glyph_id:'gap',scalar:' ',scalar_index:1,x:x+3,y:1,advance_px:2},{glyph_id:'b',scalar:'B',scalar_index:2,x:x+5,y:1,advance_px:2}];
const nameCell=align=>({id:'name',kind:'name',record_id:'name',align,style:'plain',box:{x:1,y:1,width:10,height:4},box_bounds:[1,1,11,5],text:'A B',advance_px:7,placements:placements(align==='right'?4:1),diagnostics:[],status:'PASS'});
const literal={id:'literal',kind:'literal',text:'A',align:'left',style:'plain',box:{x:0,y:6,width:2,height:2},box_bounds:[0,6,2,8],placements:[{glyph_id:'a',x:0,y:6,advance_px:3}],diagnostics:[],status:'PASS'};
const preview={ok:true,status:'PASS',source_sha256:'sha',document_id:'doc',schema_sha256:'script-schema',font_sha256:'font-sha',font_schema_sha256:'font-schema',metrics_id:'metrics',native_render_verified:false,native_font_usage_verified:false,profile:{viewport:{width:12,height:8},line_height_px:3},glyph_map:mapping,glyphs:glyphs.slice(0,3),script:structuredClone(doc),cases:[{id:'left',selected_entry:'one',cells:[nameCell('left'),literal],diagnostics:[]},{id:'right',selected_entry:null,cells:[nameCell('right')],diagnostics:[]}]};
const measured={ok:true,status:'MEASURED',source_sha256:'font-sha',font_schema_sha256:'font-schema',metrics_id:'metrics',glyphs};
const config={profile:{model:'fixed-menu-v1'},cases:{},font_artifact_id:'font',font_schema:{codec:'mono-row-msb-v1',source:{sha256:'font-sha'}}};
const nodes=new Map(),drafts=new Map(),handlers={},calls=[];
function node(value=''){return {value,hidden:false,style:{},innerHTML:'',textContent:'',listeners:{},addEventListener(event,fn){(this.listeners[event]??=[]).push(fn);},fire(event){for(const fn of this.listeners[event]||[])fn({target:this});}};}
nodes.set('script-schema',node('{}'));nodes.set('menu-config',node(JSON.stringify(config)));nodes.set('script-segment-0-0',node('A B'));nodes.set('script-capacity-0',node());
globalThis.document={getElementById:id=>nodes.get(id)||null};
const state={page:'scripts',project:{project_id:'p',sources:[],builds:[],descriptors:{}},artifact:{artifact_id:'a',sha256:'sha',name:'Synthetic ROM',descriptors:{}},results:{'script.inspect':doc}};
let html='',reply=async op=>structuredClone(op==='menu.preview'?preview:measured);
const ctx={state,sourceParams:()=>({project_id:'p',artifact_id:state.artifact.artifact_id}),projectParams:()=>({project_id:'p'}),draft:(key,fallback)=>drafts.get(key)??fallback,setDraft:(key,value)=>drafts.set(key,value),use:next=>Object.assign(handlers,next),notify(){},api:{call:async(op,p)=>{calls.push({op,p});return reply(op,p);}},render:async()=>{html=await scripts.render(ctx);}};
ctx.run=async(op,p)=>{const result=await ctx.api.call(op,p);state.results[op]=result;await ctx.render();return result;};
await ctx.render();await handlers['menu-preview']();
assert.match(html,/id="menu-original-0"/,'Preview menu must expose an actual original canvas');assert.match(html,/id="menu-edited-1"/,'each declared case has an editing canvas');
assert(calls.some(c=>c.op==='font.measure'&&c.p.artifact_id==='font'),'new name characters require all measured font glyphs');
assert.match(html,/Declared font.*layout/);assert.match(html,/not a captured game scene/);assert.doesNotMatch(html,/<details class="config" open/);

for(let i=0;i<2;i++){
 for(const kind of ['original','edited']){const canvas=node();canvas.getContext=()=>({createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData:image=>{canvas.rgba=[...image.data];}});nodes.set(`menu-${kind}-${i}`,canvas);}
 nodes.set('menu-case-status-'+i,node());
}
nodes.set('menu-visual-preview',node());scripts.mount(ctx);
const ink=id=>{const canvas=nodes.get(id),result=[];for(let i=0;i<canvas.rgba.length;i+=4)if(canvas.rgba[i]>100)result.push([i/4%12,Math.floor(i/4/12)]);return result;};
assert.deepEqual(ink('menu-original-0'),[[1,1],[1,2],[5,2],[6,2],[6,3],[0,6],[0,7]],'original pixels use exact glyph bit order, bearings and backend placements');
assert.deepEqual(ink('menu-original-1'),[[4,1],[4,2],[8,2],[9,2],[9,3]],'backend right-aligned placements are retained');
const originalPixels=[...nodes.get('menu-original-0').rgba],originalTokens=JSON.stringify(doc.records[0].tokens);
nodes.get('script-segment-0-0').value='C';nodes.get('script-segment-0-0').fire('input');
assert.deepEqual(ink('menu-edited-0'),[[9,1],[9,2],[0,6],[0,7]],'new glyph from full measurement uses row stride and MSB bit 8');
assert.deepEqual(ink('menu-edited-1'),[[10,1],[10,2]],'edited name alignment uses measured advances and the declared right edge');
assert.deepEqual(nodes.get('menu-original-0').rgba,originalPixels);assert.equal(JSON.stringify(doc.records[0].tokens),originalTokens);assert.match(nodes.get('menu-case-status-0').textContent,/Preview updated/);
nodes.get('script-segment-0-0').value='Z';nodes.get('script-segment-0-0').fire('input');assert.equal(nodes.get('menu-edited-0').hidden,true);assert.match(nodes.get('menu-case-status-0').textContent,/unavailable.*glyph/i);
nodes.get('script-segment-0-0').value='C C';nodes.get('script-segment-0-0').fire('input');assert.equal(nodes.get('menu-edited-0').hidden,false);assert.match(nodes.get('menu-case-status-0').textContent,/declared box/i);
record.tokens.push({kind:'control',control_id:'preserved'});nodes.get('script-segment-0-0').fire('input');assert.equal(nodes.get('menu-edited-0').hidden,true);assert.match(nodes.get('menu-case-status-0').textContent,/control-free/);record.tokens.pop();

// Changing declaration text invalidates a mounted canvas rather than showing an old layout.
nodes.get('menu-config').value=JSON.stringify({...config,profile:{model:'changed'}});nodes.get('menu-config').fire('input');assert.match(nodes.get('menu-visual-preview').innerHTML,/unavailable|Preview.*again/i);
nodes.get('menu-config').value=JSON.stringify(config);nodes.get('script-segment-0-0').value='A B';

// Requests are source/document/config/text-bound and a newer request wins.
const deferred=[];reply=(op,p)=>new Promise(resolve=>deferred.push({op,p,resolve}));
for(const change of [()=>{state.artifact={...state.artifact,artifact_id:'other'};},()=>{state.results['script.inspect']={...doc,document_id:'other'};},()=>{nodes.get('menu-config').value=JSON.stringify({...config,cases:{different:true}});},()=>{nodes.get('script-segment-0-0').value='C';}]){
 state.artifact={...state.artifact,artifact_id:'a'};state.results['script.inspect']=doc;nodes.get('menu-config').value=JSON.stringify(config);nodes.get('script-segment-0-0').value='A B';await ctx.render();
 const start=deferred.length,pending=handlers['menu-preview']();await new Promise(setImmediate);change();for(const entry of deferred.slice(start))entry.resolve(structuredClone(entry.op==='menu.preview'?preview:measured));await pending;await ctx.render();assert.doesNotMatch(html,/id="menu-edited-0"/,'stale work cannot install a visual preview');
}
state.artifact={...state.artifact,artifact_id:'a'};state.results['script.inspect']=doc;nodes.get('menu-config').value=JSON.stringify(config);nodes.get('script-segment-0-0').value='A B';await ctx.render();
const first=deferred.length,older=handlers['menu-preview']();await new Promise(setImmediate);const second=deferred.length,newer=handlers['menu-preview']();await new Promise(setImmediate);for(const entry of deferred.slice(second))entry.resolve(structuredClone(entry.op==='menu.preview'?preview:measured));await newer;
const current=state.menuVisual;for(const entry of deferred.slice(first,second))entry.resolve(structuredClone(entry.op==='menu.preview'?preview:measured));await older;assert.equal(state.menuVisual,current);
reply=async op=>structuredClone(op==='menu.preview'?preview:{...measured,metrics_id:'wrong'});await handlers['menu-preview']();assert.doesNotMatch(html,/id="menu-edited-0"/);assert.match(html,/unavailable/);
reply=async()=>({ok:false,status:'BLOCKED',error:{message:'Unknown declared menu layout'}});await handlers['menu-preview']();assert.match(html,/Unknown declared menu layout/);assert.doesNotMatch(html,/id="menu-edited-0"/);
// The application temporarily removes controls while rendering; setup defaults must agree.
nodes.get('menu-config').value=JSON.stringify({profile:{},cases:{},font_artifact_id:'',font_schema:{}});drafts.delete('menu-config');
ctx.render=async()=>{const configNode=nodes.get('menu-config'),schemaNode=nodes.get('script-schema');nodes.delete('menu-config');nodes.delete('script-schema');try{html=await scripts.render(ctx);}finally{nodes.set('menu-config',configNode);nodes.set('script-schema',schemaNode);}};
await ctx.render();await handlers['menu-preview']();assert.match(html,/Menu preview unavailable.*Unknown declared menu layout/,'unconfigured layouts report a useful failure through an actual render cycle');
console.log('Declared menu canvases use measured bitmap pixels/placements, update staged names and reject missing glyphs or stale declarations without native-render claims.');
