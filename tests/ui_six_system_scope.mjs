import assert from 'node:assert/strict';
import {formatLabel} from '../romancer/ui/graphics_formats.js';
const label=formatLabel('tile8-packed4-low-v1');
assert.doesNotMatch(label,/advance|gba/i);
assert.match(label,/low nibble|packed/i);
console.log('Retained generic pixel layouts do not advertise a removed console.');
