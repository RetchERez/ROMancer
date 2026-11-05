import assert from 'node:assert/strict';
import {OVERVIEW_TASKS,overviewTasks} from '../romancer/ui/overview_tasks.js';
const html=overviewTasks();assert.equal(OVERVIEW_TASKS.length,8);
for(const [id,label] of OVERVIEW_TASKS){assert(html.includes(`data-id="${id}"`));assert(html.includes(label.replace('&','&amp;')));}
assert.doesNotMatch(html,/data-id="levels"/);
assert.equal(new Set(OVERVIEW_TASKS.map(x=>x[0])).size,8);
const compact=overviewTasks(true);assert.doesNotMatch(compact,/data-id="(?:assets|scripts|tables|sound)"/);assert.match(compact,/Inspect ROM bytes/);
console.log('Overview provides eight distinct editing, investigation, testing and export destinations.');
