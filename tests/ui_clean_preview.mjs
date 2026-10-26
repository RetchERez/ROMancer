import assert from 'node:assert/strict';
import {rememberPreview,cleanPreview} from '../romancer/ui/clean_preview.js';
import {differencePixels} from '../romancer/ui/visual_comparison.js';
const a={width:1,height:1},b={width:1,height:1},raw=new Uint8ClampedArray([10,20,30,255]);
rememberPreview(a,1,1,raw);rememberPreview(b,1,1,raw,{note:'Terrain graphics only'});raw[0]=255;
assert.equal(cleanPreview(b).pixels[0],10,'snapshot does not inherit later cursor/overlay mutations');assert.equal(differencePixels(cleanPreview(a).pixels,cleanPreview(b).pixels).changed,0);
rememberPreview(b,1,1,new Uint8ClampedArray([11,20,30,255]));assert.equal(differencePixels(cleanPreview(a).pixels,cleanPreview(b).pixels).changed,1);
b.width=2;assert.equal(cleanPreview(b),null,'resized canvases cannot reuse stale snapshots');assert.equal(cleanPreview({width:1,height:1}),null);
console.log('Comparisons use clean immutable model pixels and never infer changes from editor overlays.');
