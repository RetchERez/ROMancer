export function roomValue(v,point){
 if(!v.object.allowed.some(p=>p[0]===point[0]&&p[1]===point[1]))throw Error('Choose a verified floor tile highlighted in the room.');
 if(point[0]===v.original[0]&&point[1]===v.original[1])return 'original';
 if(point[0]===v.stool_down[0]&&point[1]===v.stool_down[1])return 'stool_down';
 return `at:${point[0]},${point[1]}`;
}
export function roomTarget(v,value){
 const match=/^at:(\d+),(\d+)$/.exec(value||'');
 return value==='original'?v.original:value==='stool_down'?v.stool_down:match?[Number(match[1]),Number(match[2])]:v.current;
}
export function roomPoint(v,rect,point){
 if(rect.width<=0||rect.height<=0)return null;
 const x=Math.floor((point.x-rect.left)/rect.width*v.size[0]),y=Math.floor((point.y-rect.top)/rect.height*v.size[1]);
 return x>=0&&y>=0&&x<v.size[0]&&y<v.size[1]?[v.origin[0]+x,v.origin[1]+y]:null;
}
export function roomPixels(v,point,{terrain=true,object=true}={}){
 const size=v.tile_size,width=v.size[0]*size,height=v.size[1]*size;
 if(width*height>1024*1024)throw Error('Room preview exceeds its pixel budget.');
 const cells=[...v.base_cells],x=point[0]-v.origin[0],y=point[1]-v.origin[1];
 if(x<0||y<0||x>=v.size[0]||y>=v.size[1])throw Error('Object is outside the decoded room.');
 if(object)cells[y*v.size[0]+x]=v.object.tile_id;
 const rgba=new Uint8ClampedArray(width*height*4);
 cells.forEach((id,cell)=>{
  const tile=v.tiles[id];if(!tile||tile.length!==size*size)throw Error('A room tile is missing from its verified tileset.');
  tile.forEach((index,pixel)=>{const color=v.palette[index];if(!color)throw Error('Room pixel has no declared color.');const rgb=terrain||(object&&cell===y*v.size[0]+x)?color:[16,25,31],px=cell%v.size[0]*size+pixel%size,py=Math.floor(cell/v.size[0])*size+Math.floor(pixel/size);rgba.set([...rgb,255],(py*width+px)*4);});
 });return rgba;
}
export function roomPreview(v,value){
 const point=roomTarget(v,value),changed=point.some((n,i)=>n!==v.current[i]);
 return `<div class="live-game-preview room-object-preview"><h3>Opening bedroom</h3><fieldset class="room-layers"><legend>Layers</legend><label><input id="room-show-terrain" type="checkbox" checked> Terrain</label><label><input id="room-show-object" type="checkbox" checked> Objects</label>${v.collision_values?'<label><input id="room-show-collision" type="checkbox"> Collision values</label>':''}<label><input id="room-show-grid" type="checkbox"> Tile grid</label><label><input id="room-show-targets" type="checkbox" checked> Allowed floor tiles</label></fieldset><div class="preview-pair"><div><span>Original</span><canvas id="room-original" aria-label="Decoded original bedroom map"></canvas></div><div><span>Editing - move here</span><canvas id="room-edit" tabindex="0" role="application" aria-label="Decoded bedroom: drag stool or use arrow keys to move it"></canvas></div></div><p id="room-edit-status" role="status">${changed?'Stool preview updated. Create a build to keep this change.':'No changes yet.'}</p><p class="preview-caption">Drag the stool onto a highlighted floor tile. You can also click a floor tile or use the arrow keys.</p><details><summary>Preview details</summary><p>The room background and stool come from this ROM. Characters and dialogue appear in Playtest. Exits and other objects are protected.</p><p>Collision values show stored numbers; their meanings are not inferred. Review changes, then create a build.</p></details></div>`;
}
export function mountRoomPreview(ctx,v,value,change){
 const canvas=document.getElementById('room-edit'),original=document.getElementById('room-original');if(!canvas||!original)return;
 const selected=roomTarget(v,value),width=v.size[0]*v.tile_size,height=v.size[1]*v.tile_size;
 const source=ctx.state.gameVisualModel,alive=()=>ctx.state.gameVisualModel===source&&canvas.isConnected;
 let point=selected,pointer=null;
 const layerIds=['room-show-terrain','room-show-object','room-show-collision','room-show-grid','room-show-targets'];
 if(ctx.state.roomLayerScope!==source.scope){ctx.state.roomLayerScope=source.scope;ctx.state.roomLayers={};}
 for(const id of layerIds){const input=document.getElementById(id);if(input&&Object.hasOwn(ctx.state.roomLayers,id))input.checked=ctx.state.roomLayers[id];}
 const enabled=id=>document.getElementById(id)?.checked??true;
 const paint=(node,position,targets=false)=>{
  node.width=width;node.height=height;const c=node.getContext('2d'),image=c.createImageData(width,height);image.data.set(roomPixels(v,position,{terrain:enabled('room-show-terrain'),object:enabled('room-show-object')}));c.putImageData(image,0,0);
  if(v.collision_values&&enabled('room-show-collision'))v.collision_values.forEach((value,index)=>{const x=index%v.size[0]*v.tile_size,y=Math.floor(index/v.size[0])*v.tile_size;c.fillStyle=value===1?'#16775b88':'#74427288';c.fillRect(x,y,v.tile_size,v.tile_size);c.fillStyle='#fff';c.font='6px monospace';c.fillText(value.toString(16).padStart(2,'0'),x+2,y+8);});
  if(enabled('room-show-grid')){c.strokeStyle='#ffffff60';c.lineWidth=.5;for(let y=0;y<v.size[1];y++)for(let x=0;x<v.size[0];x++)c.strokeRect(x*v.tile_size+.5,y*v.tile_size+.5,v.tile_size-1,v.tile_size-1);}
  if(targets&&document.getElementById('room-show-targets')?.checked){c.strokeStyle='#26b99a';c.lineWidth=1;for(const p of v.object.allowed)c.strokeRect((p[0]-v.origin[0])*v.tile_size+.5,(p[1]-v.origin[1])*v.tile_size+.5,v.tile_size-1,v.tile_size-1);}
  if(targets&&enabled('room-show-object')){c.strokeStyle='#e8b34f';c.lineWidth=2;c.strokeRect((position[0]-v.origin[0])*v.tile_size+1,(position[1]-v.origin[1])*v.tile_size+1,v.tile_size-2,v.tile_size-2);}
 };
 const status=text=>{const node=document.getElementById('room-edit-status');if(node)node.textContent=text;};
 const propose=next=>{if(!next)return false;if(!enabled('room-show-object')){status('Enable the Objects layer to move the stool.');return false;}try{roomValue(v,next);point=next;paint(canvas,point,true);status(`Move stool to (${point.join(', ')}) - release to stage`);return true;}catch(e){status(e.message);return false;}};
 const pick=e=>roomPoint(v,canvas.getBoundingClientRect(),{x:e.clientX,y:e.clientY});
 canvas.style.touchAction='none';
 canvas.addEventListener('pointerdown',e=>{if(!alive()||e.button!==0)return;e.preventDefault();canvas.focus();pointer=e.pointerId;canvas.setPointerCapture(pointer);propose(pick(e));});
 canvas.addEventListener('pointermove',e=>{if(alive()&&pointer===e.pointerId)propose(pick(e));});
 canvas.addEventListener('pointerup',e=>{if(!alive()||pointer!==e.pointerId)return;pointer=null;const next=pick(e);if(next&&propose(next)){change(roomValue(v,point));}else{point=selected;paint(canvas,point,true);}});
 canvas.addEventListener('pointercancel',()=>{if(!alive())return;pointer=null;point=selected;paint(canvas,point,true);status('Move cancelled.');});
 canvas.addEventListener('keydown',e=>{const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(!alive()||!delta||e.ctrlKey||e.altKey||e.metaKey)return;e.preventDefault();const next=[point[0]+delta[0],point[1]+delta[1]];if(propose(next))change(roomValue(v,next));});
 for(const id of layerIds)document.getElementById(id)?.addEventListener('change',e=>{ctx.state.roomLayers[id]=e.target.checked;paint(original,v.current);paint(canvas,point,true);});
 paint(original,v.current);paint(canvas,selected,true);
}
