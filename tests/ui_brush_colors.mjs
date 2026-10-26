import assert from 'node:assert/strict';
import {brushColors} from '../romancer/ui/brush_colors.js';
const bitmap={codec:'tile8-paired2-msb-v1'};
let colors=brushColors(bitmap,null,null);assert.equal(colors.length,4);assert(colors.every(c=>c.origin==='grayscale'));assert.deepEqual(colors[1].rgb,[90,90,90]);
colors=brushColors(bitmap,{colors_per_bank:4,entries:[{bank:0,index:1,rgb:{r:200,g:10,b:40}}]},null);assert.equal(colors[1].origin,'declared');assert.deepEqual(colors[1].rgb,[200,10,40]);assert.equal(colors[0].origin,'grayscale');
colors=brushColors(bitmap,null,{colors:[{1:[255,0,0]},{1:[0,255,0]}]});assert.equal(colors[1].origin,'observed');assert.equal(colors[1].colors.length,2);
assert.equal(brushColors({codec:'unknown'},null,null).length,0);
console.log('Brush swatches distinguish declared, observed and unknown grayscale colors and preserve stored indices.');
