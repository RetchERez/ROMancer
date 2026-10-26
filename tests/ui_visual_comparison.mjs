import assert from 'node:assert/strict';
import {differencePixels,blinkAllowed} from '../romancer/ui/visual_comparison.js';
const before=new Uint8ClampedArray([1,2,3,255,4,5,6,255]),after=new Uint8ClampedArray([1,2,3,255,4,9,6,255]);
const result=differencePixels(before,after);assert.equal(result.changed,1);assert.deepEqual([...result.pixels],[0,0,0,0,4,9,6,255]);assert.deepEqual([...before],[1,2,3,255,4,5,6,255]);assert.deepEqual([...after],[1,2,3,255,4,9,6,255]);
assert.throws(()=>differencePixels(before,new Uint8ClampedArray(4)),/dimensions/);assert.equal(blinkAllowed(true,false),false);assert.equal(blinkAllowed(false,true),false);assert.equal(blinkAllowed(false,false),true);
console.log('Difference views preserve both originals and edits, mask unchanged pixels, and honor reduced motion.');
