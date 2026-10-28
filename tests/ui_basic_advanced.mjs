import assert from 'node:assert/strict';
import {BASIC_PAGES,ADVANCED_PAGES} from '../romancer/ui/navigation.js';
assert.ok(BASIC_PAGES.includes('tables'));assert.ok(BASIC_PAGES.includes('assets'));assert.ok(!BASIC_PAGES.includes('debug'));
assert.ok(ADVANCED_PAGES.includes('debug'));assert.ok(ADVANCED_PAGES.includes('automation'));
assert.equal(new Set([...BASIC_PAGES,...ADVANCED_PAGES]).size,BASIC_PAGES.length+ADVANCED_PAGES.length);
console.log('Basic navigation keeps visual editors and values visible; technical investigations are under Advanced.');
