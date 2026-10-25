import assert from 'node:assert/strict';
import {finderTarget,matchingFinder} from '../romancer/ui/value_finder.js';
assert.equal(finderTarget(''),null);assert.equal(finderTarget('0xff'),255);assert.equal(finderTarget('-3'),-3);assert.throws(()=>finderTarget('1.5'));
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'}};
assert.equal(matchingFinder(state,{selection_scope:'p:a:s',source_sha256:'s'}),true);
state.artifact.sha256='other';assert.equal(matchingFinder(state,{selection_scope:'p:a:s',source_sha256:'s'}),false);
console.log('RAM narrowing parses only integer targets and keeps observations bound to the selected source.');
