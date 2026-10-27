import {esc} from './common.js';

export function collisionBrushes(room,values){
 const rows=(room.collision_types||[]).map(row=>({...row})),known=new Set(rows.map(row=>row.value));
 for(const value of [...new Set(values)].sort((a,b)=>a-b))if(!known.has(value))rows.push({value,name:'Raw value '+value,kind:'unmapped',color:[110,130,150]});
 return rows;
}
export function collisionPalette(room,values,selected){
 return `<div class="level-collision-palette" role="group" aria-label="Collision brushes">${collisionBrushes(room,values).map(row=>`<button type="button" data-level-collision="${row.value}" aria-pressed="${Number(selected)===row.value}"><span class="collision-swatch" style="background:rgb(${row.color.join(',')})" aria-hidden="true"></span><strong>${esc(row.name)}</strong><span>${row.value} · ${esc(row.kind)}</span></button>`).join('')}</div>`;
}
export function actorHitboxes(doc,model,id){
 const room=doc.rooms.find(row=>row.id===id),metadata=room?.object_metadata||doc.definition?.rooms?.find(row=>row.id===id)?.object_metadata||[],objects=model.objects(id);
 return metadata.flatMap(row=>{
  const object=objects[row.index],box=row.hitbox;if(!box||!object||!Number.isSafeInteger(object.x)||!Number.isSafeInteger(object.y))return [];
  const [ox,oy,width,height]=['offset_x','offset_y','width','height'].map(key=>object[box[key]]);
  if(![ox,oy,width,height].every(Number.isSafeInteger)||ox<0||oy<0||width<1||height<1)return [];
  return [{index:row.index,name:row.name,left:object.x*doc.block_width*8+ox,top:object.y*doc.block_height*8+oy,width,height}];
 });
}
export function objectFieldLabel(field,metadata){
 const component=Object.entries(metadata?.hitbox||{}).find(([,name])=>name===field.name)?.[0];
 if(component)return ({offset_x:'Hitbox left offset (pixels)',offset_y:'Hitbox top offset (pixels)',width:'Hitbox width (pixels)',height:'Hitbox height (pixels)'})[component];
 return ({x:'X position (cells)',y:'Y position (cells)',starting_health:'Starting health',contact_damage:'Contact damage',ai_enabled:'Movement enabled (0 off, 1 on)',patrol_left:'Left movement limit (cells)',patrol_right:'Right movement limit (cells)',damage_cooldown:'Damage cooldown (frames)'})[field.name]||field.name;
}

export function paintStartingSprites(doc,model,id,pixels,width,height){
 const room=doc.rooms.find(row=>row.id===id),metadata=room?.object_metadata||[],objects=model.objects(id);
 for(const entry of metadata){const sprite=entry.sprite,object=objects[entry.index];if(!sprite||!Number.isSafeInteger(object?.x)||!Number.isSafeInteger(object?.y))continue;
  const left=object.x*doc.block_width*8,top=object.y*doc.block_height*8;
  for(const [part,index] of sprite.tiles.entries())for(const [pixel,value] of doc.tiles[index].entries()){
   if(value===sprite.transparent_index)continue;
   const x=left+part%sprite.width*8+pixel%8,y=top+Math.floor(part/sprite.width)*8+Math.floor(pixel/8);
   if(x>=0&&x<width&&y>=0&&y<height)pixels.set([...doc.palette[value],255],(y*width+x)*4);
  }
 }
 return pixels;
}
