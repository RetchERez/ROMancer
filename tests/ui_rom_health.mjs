import assert from 'node:assert/strict';
import {romHealthPanel} from '../romancer/ui/rom_health.js';
const state={artifact:{artifact_id:'one'},results:{'rom.check':{artifact_id:'two',crc32:'STALECRC'}}};
const ctx={state,draft:(_key,fallback)=>fallback};
let html=romHealthPanel(ctx);assert.ok(!html.includes('STALECRC'));assert.ok(html.includes('Expected CRC32 (optional)'));assert.ok(html.includes('Check ROM'));
state.results['rom.check']={artifact_id:'one',crc32:'CBF43926',status:'ISSUES_FOUND',crc_comparison:{status:'FAIL',expected:'00000000',measured:'CBF43926',scope:'file'},checks:[{name:'Header checksum',status:'FAIL',detail:'Header differs.',stored:'AB',computed:'CD'}]};
html=romHealthPanel(ctx);assert.ok(html.includes('CRC32 mismatch'));assert.ok(html.includes('00000000'));assert.ok(html.includes('CBF43926'));assert.ok(html.includes('AB'));assert.ok(html.includes('CD'));
state.results['rom.check'].crc_comparison.status='NOT_CHECKED';html=romHealthPanel(ctx);assert.ok(html.includes('No reference supplied'));assert.ok(!html.includes('CRC32 mismatch'));
console.log('ROM health labels distinguish measured CRC, reference mismatch, console checksums and stale selections.');
