import assert from 'node:assert/strict';
import {OVERVIEW_TASKS,overviewTasks} from '../romancer/ui/overview_tasks.js';
const html=overviewTasks();assert.equal(OVERVIEW_TASKS.length,7);
for(const [id,label] of OVERVIEW_TASKS){assert(html.includes(`data-id="${id}"`));assert(html.includes(label.replace('&','&amp;')));}
assert.doesNotMatch(html,/data-id="levels"/);
assert.equal(new Set(OVERVIEW_TASKS.map(x=>x[0])).size,7);
console.log('Overview provides eight distinct editing, investigation, testing and export destinations.');
