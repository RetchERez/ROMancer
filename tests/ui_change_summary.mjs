import assert from 'node:assert/strict';
import {changeSummary} from '../romancer/ui/change_summary.js';
assert.deepEqual(changeSummary({ok:true,workbench_plan_id:'p',hunks:[{offset:0,before_hex:'8100',after_hex:'c100'}],integrity_edits:[{offset:4,before:'0000',after:'0100'}]}),{changedBytes:2,ranges:2,integrityBytes:1});
assert.equal(changeSummary({ok:false,plan_id:'p',edits:[{offset:0,before:'00',after:'01'}]}),null);
assert.equal(changeSummary({ok:true,status:'MEASURED',count:5}),null);
assert.deepEqual(changeSummary({ok:true,plan_id:'p',edits:[{offset:0,before:'00',after:'01'},{offset:0,before:'00',after:'01'}]}).changedBytes,1);
assert.equal(changeSummary({ok:true,plan_id:'p',edits:[{offset:0,before:'zz',after:'01'}]}),null);
console.log('Review summaries count exact changed bytes, including integrity updates, without invented meanings.');
