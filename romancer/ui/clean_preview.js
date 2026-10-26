const previews=new WeakMap();
export function rememberPreview(canvas,width,height,pixels,{note=''}={}){
 if(!canvas||!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<1||height<1||width*height>1024*1024||pixels.length!==width*height*4){if(canvas)previews.delete(canvas);return false;}
 previews.set(canvas,{width,height,pixels:new Uint8ClampedArray(pixels),kind:'pixels',note});return true;
}
export function cleanPreview(canvas){const value=previews.get(canvas);return value&&value.width===canvas.width&&value.height===canvas.height?value:null;}
