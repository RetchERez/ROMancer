function checkedPixels(pixels,width,height,colorCount){
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>32||height>32||!Array.isArray(pixels)||pixels.length!==width*height)throw new Error('Tile dimensions do not match the pixel buffer.');
 if(!Number.isInteger(colorCount)||colorCount<2||colorCount>256||pixels.some(value=>!Number.isInteger(value)||value<0||value>=colorCount))throw new Error('A pixel index is outside the destination palette.');
 return [...pixels];
}
export function transformPixels(pixels,width,height,operation,color=0,colorCount=256){
 const source=checkedPixels(pixels,width,height,colorCount),output=[...source];
 if(!['fill','clear','flip-x','flip-y','rotate-cw','rotate-ccw'].includes(operation))throw new Error('Choose a supported tile transform.');
 if(operation==='fill'){
  if(!Number.isInteger(color)||color<0||color>=colorCount)throw new Error('Choose a color index inside the palette.');
  return output.fill(color);
 }
 if(operation==='clear')return output.fill(0);
 if(operation.startsWith('rotate')&&width!==height)throw new Error('90 degree rotation requires a square tile.');
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){
  const index=operation==='flip-x'?y*width+(width-1-x):operation==='flip-y'?(height-1-y)*width+x:operation==='rotate-cw'?(height-1-x)*width+y:x*width+(width-1-y);
  output[y*width+x]=source[index];
 }
 return output;
}
export function copyTile(pixels,width,height,colorCount){return {format:'romancer-tile-v1',width,height,pixels:checkedPixels(pixels,width,height,colorCount)};}
export function pasteTile(clipboard,width,height,colorCount){
 if(!clipboard||typeof clipboard!=='object'||Object.keys(clipboard).sort().join(',')!=='format,height,pixels,width'||clipboard.format!=='romancer-tile-v1')throw new Error('Copy a tile inside ROMancer first.');
 if(clipboard.width!==width||clipboard.height!==height)throw new Error('Clipboard tile dimensions differ from this cell.');
 return checkedPixels(clipboard.pixels,width,height,colorCount);
}
export function mergeCellChanges(changes,incoming){
 if(!Array.isArray(changes)||!Array.isArray(incoming)||changes.length>1024||incoming.length>1024)throw new Error('Review at most1024 asset changes at a time.');
 const keys=new Set();
 for(const change of incoming){
  if(change.kind!=='cell'||typeof change.bitmap_id!=='string'||!Number.isSafeInteger(change.cell_index)||change.cell_index<0||!Array.isArray(change.before_pixels)||!Array.isArray(change.after_pixels)||change.before_pixels.length!==change.after_pixels.length||change.before_pixels.length>1024)throw new Error('Invalid staged tile change.');
  keys.add(change.bitmap_id+':'+change.cell_index);
 }
 const merged=[...changes.filter(change=>change.kind!=='cell'||!keys.has(change.bitmap_id+':'+change.cell_index)),...incoming.filter(change=>JSON.stringify(change.before_pixels)!==JSON.stringify(change.after_pixels))];
 if(merged.length>1024)throw new Error('Review at most1024 asset changes at a time.');
 return JSON.parse(JSON.stringify(merged));
}
