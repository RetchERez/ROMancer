import {esc,button,select} from './common.js';
import {objectFieldLabel} from './level_semantics.js';

export function objectMetadata(doc,id,index){
 const room=doc.rooms.find(room=>room.id===id),definition=doc.definition?.rooms?.find(room=>room.id===id);
 return (room?.object_metadata||definition?.object_metadata||[]).find(entry=>entry.index===index)||null;
}

export function objectFields(doc,id){
 const definition=doc.definition?.rooms?.find(room=>room.id===id);
 return definition?.objects?.fields||Object.keys(doc.rooms.find(room=>room.id===id)?.objects[0]||{}).map(name=>({name,maximum:65535}));
}

export function objectMaximum(doc,id,field){
 const room=doc.rooms.find(room=>room.id===id);
 return Math.min(field.maximum??65535,field.name==='x'?room.width-1:field.name==='y'?room.height-1:field.name==='exit_room'?doc.rooms.length-1:65535);
}

export function roomConnections(doc,model){
 const result=[];
 for(const room of doc.rooms){const objects=model.objects(room.id);
  for(let index=0;index<objects.length;index++){const metadata=objectMetadata(doc,room.id,index);if(metadata?.role!=='exit'||!metadata.reference)continue;
   const field=metadata.reference.field,value=objects[index][field],target=metadata.reference.targets.find(target=>target.value===value);
   if(target)result.push({room_id:room.id,index,name:metadata.name,field,value,target_room_id:target.room_id});
  }
 }
 return result;
}

export function roomThumbnail(doc,model,id){
 const room=model.room(id),sourceWidth=room.width*doc.block_width*8,sourceHeight=room.height*doc.block_height*8;
 const scale=Math.min(1,160/sourceWidth,96/sourceHeight),width=Math.max(1,Math.floor(sourceWidth*scale)),height=Math.max(1,Math.floor(sourceHeight*scale));
 const pixels=new Uint8ClampedArray(width*height*4),cells=model.cells(id,'terrain'),blocks=model.blocks();
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){
  const sx=Math.floor(x*sourceWidth/width),sy=Math.floor(y*sourceHeight/height),bx=Math.floor(sx/(doc.block_width*8)),by=Math.floor(sy/(doc.block_height*8));
  const part=Math.floor(sy/8)%doc.block_height*doc.block_width+Math.floor(sx/8)%doc.block_width;
  const tile=blocks[cells[by*room.width+bx]][part],value=doc.tiles[tile][sy%8*8+sx%8];pixels.set([...doc.palette[value],255],(y*width+x)*4);
 }
 return {width,height,pixels};
}

export function roomNavigation(doc,model,id){
 const connections=roomConnections(doc,model),names=new Map(doc.rooms.map(room=>[room.id,room.name]));
 if(doc.rooms.length===1&&!connections.length)return '';
 return `<section class="level-room-navigation"><h3>Choose a room</h3><p class="subtle">Select an object to move it, or choose a terrain brush to paint.</p><div class="level-room-list">${doc.rooms.map(room=>{const count=connections.filter(connection=>connection.room_id===room.id).length;return `<button type="button" class="level-room-card" data-action="levels-open-room" data-id="${esc(room.id)}" aria-pressed="${room.id===id}"><canvas data-level-room-preview="${esc(room.id)}" aria-hidden="true"></canvas><strong>${esc(room.name)}</strong><span>${count} room ${count===1?'link':'links'}</span></button>`;}).join('')}</div><div class="level-connection-list">${connections.map(connection=>`<div class="level-connection"><span>${esc(names.get(connection.room_id))}</span>${button(connection.name,'levels-select-object',{id:String(connection.index),name:connection.room_id})}<span aria-hidden="true">→</span>${button(names.get(connection.target_room_id),'levels-open-room',{id:connection.target_room_id})}</div>`).join('')}</div></section>`;
}

function objectChoices(doc,model,id,allRecords=false){
 return model.objects(id).flatMap((object,index)=>{const metadata=objectMetadata(doc,id,index);return metadata||allRecords?[{index,object,metadata,label:metadata?.name||'Record '+index}]:[];});
}

export function visibleLevelObjects(doc,model,id,mode='objects'){
 if(!['objects','records'].includes(mode))return [];
 const room=model.room(id);
 return objectChoices(doc,model,id,mode==='records').filter(({object})=>Number.isSafeInteger(object.x)&&Number.isSafeInteger(object.y)&&object.x>=0&&object.x<room.width&&object.y>=0&&object.y<room.height);
}

export function selectedObjectIndex(ctx,model,id){
 const choices=objectChoices(model.doc,model,id,ctx.draft('level-overlay','objects')==='records'),value=Number(ctx.draft('level-object-index','0'));
 return choices.find(choice=>choice.index===value)?.index??choices[0]?.index??null;
}

export function objectInspector(ctx,doc,model,id){
 const allRecords=ctx.draft('level-overlay','objects')==='records',choices=objectChoices(doc,model,id,allRecords);
 if(!choices.length)return `<section class="card level-object-inspector"><h3>Objects</h3><p>No named objects in this room.</p>${model.objects(id).length?'<details><summary>Advanced records</summary><p>Choose All records (Advanced) in Overlay to inspect or move raw record slots.</p></details>':''}</section>`;
 const index=selectedObjectIndex(ctx,model,id),object=model.objects(id)[index],metadata=objectMetadata(doc,id,index),reference=metadata?.role==='exit'?metadata.reference:null;
 const names=new Map(doc.rooms.map(room=>[room.id,room.name]));
 const destination=reference?select('level-object-destination','Destination room',reference.targets.map(target=>[target.value,names.get(target.room_id)]),object[reference.field]):'';
 const fields=objectFields(doc,id),controls=fields.map((field,position)=>{
  if(reference?.field===field.name)return '';
  const maximum=objectMaximum(doc,id,field),minimum=field.minimum??0,label=objectFieldLabel(field,metadata);
  return `<label class="field"><span>${esc(label)}</span><input id="level-object-input-${position}" type="number" min="${minimum}" max="${maximum}" step="1" value="${object[field.name]}"><small>${minimum} to ${maximum}</small></label>`;
 });
 const positions=controls.filter((_,i)=>['x','y'].includes(fields[i].name)).join(''),advanced=controls.filter((_,i)=>!['x','y'].includes(fields[i].name)).join('');
 const instruction=Number.isSafeInteger(object.x)&&Number.isSafeInteger(object.y)?"Choose Move object, then drag its label on the map.":'This object has no map position. Its values are available below.';
 return `<section class="card level-object-inspector"><h3>${allRecords?'Records (Advanced)':'Objects'}</h3>${select('level-object-index','Selected object',choices.map(choice=>[choice.index,choice.label]),index)}<p class="subtle">${instruction}</p>${destination}<div class="field-row">${positions}</div><details class="level-object-advanced"><summary>${metadata?.hitbox?'Hitbox & behavior · Advanced':'Other values · Advanced'}</summary>${metadata?.hitbox?'<p class="subtle">Hitboxes show the starting position. Build and playtest to check contact during movement.</p>':''}<div class="field-row">${advanced}</div><p class="subtle">These values come from the layout definition. Names and roles do not establish game behavior.</p><details><summary>Raw record</summary><pre>${esc(JSON.stringify(object,null,2))}</pre></details></details>${button('Update preview','levels-object-apply')}</section>`;
}

export function mountRoomNavigation(doc,model){
 for(const canvas of document.querySelectorAll?.('[data-level-room-preview]')||[]){
  const picture=roomThumbnail(doc,model,canvas.dataset.levelRoomPreview);canvas.width=picture.width;canvas.height=picture.height;
  const context=canvas.getContext('2d'),image=context.createImageData(picture.width,picture.height);image.data.set(picture.pixels);context.putImageData(image,0,0);
 }
}
