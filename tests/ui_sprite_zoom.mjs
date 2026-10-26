import assert from 'node:assert/strict';
import {spritePreviewSize} from '../romancer/ui/sprite_assembly.js';
assert.deepEqual(spritePreviewSize(8,8,'fit',410),{width:256,height:256,scale:32});
assert.deepEqual(spritePreviewSize(16,32,'fit',410),{width:192,height:384,scale:12});
assert.deepEqual(spritePreviewSize(64,64,'fit',210),{width:192,height:192,scale:3});
assert.deepEqual(spritePreviewSize(8,8,'16',410),{width:128,height:128,scale:16});
assert.deepEqual(spritePreviewSize(64,64,'32',210),{width:2048,height:2048,scale:32});
assert.deepEqual(spritePreviewSize(8,8,'invalid',410),spritePreviewSize(8,8,'fit',410));
console.log('Sprite previews use integer zoom, fit available space, and preserve raw dimensions.');
