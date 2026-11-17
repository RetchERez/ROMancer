// Pure helpers for pictures (8x8 tiles) and backgrounds in the Scenes editor:
// reading and drawing a picture, the tools of the pixel editor, and where a
// background layer's cells sit on the recorded screen.
export const MODES=[['colors','Colors','Change a color of the palette'],['graphics','Graphics','Redraw a picture, pixel by pixel'],['background','Background','Change which picture a background cell shows']];
export function parsePixels(text,bits){const step=bits>4?2:1,out=[];for(let i=0;i<text.length;i+=step)out.push(parseInt(text.slice(i,i+step),16));return out;}
export const pixelText=(pixels,bits)=>pixels.map(p=>p.toString(16).padStart(bits>4?2:1,'0')).join('');

// The colors a picture is shown with: one line of the scene's palette.
export function tilePalette(tile,colors,line=tile.line||0){
 const [base,step,size]=tile.pal,out=[];
 for(let p=0;p<size;p++)out.push(colors[base+line*step+p]||[0,0,0]);
 if(tile.zero==='backdrop'&&colors[0])out[0]=colors[0];
 return out;
}
export const sameTile=(a,b)=>a.length===b.length&&a.every((value,index)=>value===b[index]);
export function flipTile(pixels,way){const out=[];for(let y=0;y<8;y++)for(let x=0;x<8;x++)out.push(way==='h'?pixels[y*8+7-x]:pixels[(7-y)*8+x]);return out;}
export function fillTile(pixels,x,y,value){
 const out=[...pixels],from=out[y*8+x];if(from===value)return out;
 const todo=[[x,y]];
 while(todo.length){const [px,py]=todo.pop();if(px<0||py<0||px>7||py>7||out[py*8+px]!==from)continue;out[py*8+px]=value;todo.push([px+1,py],[px-1,py],[px,py+1],[px,py-1]);}
 return out;
}
export function nearestInk(rgb,palette){let best=0,distance=Infinity;palette.forEach((color,index)=>{const d=(color[0]-rgb[0])**2+(color[1]-rgb[1])**2+(color[2]-rgb[2])**2;if(d<distance){best=index;distance=d;}});return best;}
// An imported picture (RGBA, 8x8) becomes palette numbers; see-through pixels take color 0.
export function importPixels(rgba,palette){const out=[];for(let i=0;i<64;i++)out.push(rgba[i*4+3]<128?0:nearestInk([rgba[i*4],rgba[i*4+1],rgba[i*4+2]],palette));return out;}
export function tileRgba(pixels,palette,clear=false){
 const out=new Uint8ClampedArray(256);
 pixels.forEach((p,i)=>{const color=palette[p]||[0,0,0];out[i*4]=color[0];out[i*4+1]=color[1];out[i*4+2]=color[2];out[i*4+3]=clear&&p===0?0:255;});
 return out;
}
export function howLabel(tile){
 if(!tile.editable)return 'Locked';
 return {direct:'Can be changed in place',packed:'Packed in the ROM',patch:'Needs a small patch'}[tile.how]||'Can be changed';
}

// ---- a background layer on the recorded screen. A band is [first line, line after the last, scrolled across, scrolled down].
const wrap=(value,size)=>((value%size)+size)%size;
export function bandAt(layer,y){return layer.bands.find(band=>y>=band[0]&&y<band[1])||null;}
export function cellAt(layer,x,y){
 const band=bandAt(layer,y);if(!band)return null;
 const size=layer.cell,mx=wrap(x+band[2],layer.width*size),my=wrap(y+band[3],layer.height*size),cx=Math.floor(mx/size),cy=Math.floor(my/size);
 return {cx,cy,index:cy*layer.width+cx,left:x-mx%size,top:y-my%size};
}
// Every place a cell is drawn on a screen of this size, clipped to the band it is drawn in.
export function cellRects(layer,cx,cy,width,height){
 const size=layer.cell,wide=layer.width*size,tall=layer.height*size,out=[];
 for(const [first,last,sx,sy] of layer.bands)for(let top=wrap(cy*size-sy,tall)-tall;top<last;top+=tall){
  if(top+size<=first)continue;
  for(let left=wrap(cx*size-sx,wide)-wide;left<width;left+=wide)if(left+size>0)out.push({x:left,y:top,size,first:Math.max(first,top),last:Math.min(last,top+size)});
 }
 return out.filter(rect=>rect.last>rect.first&&rect.first<height);
}
// Grid lines for one band: [[x...],[y...]] in screen pixels.
export function bandGrid(layer,band,width){
 const size=layer.cell,xs=[],ys=[];
 for(let x=wrap(-band[2],size);x<=width;x+=size)xs.push(x);
 for(let y=band[0];y<=band[1];y++)if(wrap(y+band[3],size)===0)ys.push(y);
 return [xs,ys];
}
// Cells that are stored in the same place in the ROM as the given ones: they change together.
export function sharedCells(layer,indices){
 const source=layer.cells.source,wanted=new Set(indices.map(index=>source[index]).filter(value=>value>=0)),chosen=new Set(indices),out=[];
 if(!wanted.size)return out;
 source.forEach((value,index)=>{if(wanted.has(value)&&!chosen.has(index))out.push(index);});
 return out;
}
export const cellState=(layer,index)=>({r:'plain',c:'plain',d:'packed',u:'locked'}[layer.cells.status[index]]||'locked');
export function cellNow(layer,index,tileFor){
 const flags=layer.cells.flags[index];
 return {tile:tileFor(layer.cells.tile[index]),hflip:!!(flags&1),vflip:!!(flags&2),line:layer.cells.line[index]};
}
export const layerLabel=layer=>`${layer.name[0].toUpperCase()+layer.name.slice(1)}${layer.placed?` (seen on ${layer.seen}% of the screen)`:' (not found on this screen)'}`;
export function bestLayer(layers){let best=null;for(const layer of layers)if(layer.placed&&(!best||layer.seen>best.seen))best=layer;return best||layers[0]||null;}
export const checkTone=state=>state==='good'?'notice':state==='working'?'notice quiet':'notice warm';
// The workbench sends a big scene in a compact form: what pictures share sits in one table, and a layer's cells are strings.
export function expandGraphics(gfx){
 if(!gfx.kinds)return gfx;
 const tiles=gfx.tiles.map(row=>{const [domain,address,format]=row.id.split(':');return {...gfx.kinds[row.k],id:row.id,name:row.name,pixels:row.pixels,line:row.line,uses:row.uses,on_screen:!!row.on,domain,address:Number(address),format,blank:new Set(row.pixels).size<2,pending:row.pending||null,notes:row.notes||[],details:row.at>=0?[row.at]:[]};});
 const layers=gfx.layers.map(layer=>typeof layer.cells.tile!=='string'?layer:{...layer,cells:{tile:layer.cells.tile.split(',').map(Number),flags:[...layer.cells.flags].map(Number),line:[...layer.cells.line].map(Number),status:layer.cells.status,source:layer.cells.source.split(',').map(Number)}});
 return {...gfx,tiles,layers};
}
