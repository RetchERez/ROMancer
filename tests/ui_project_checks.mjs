import assert from 'node:assert/strict';
import {projectChecks,supportControls} from '../romancer/ui/project_checks.js';
const state={project:{project_id:'p'},projectValidation:{project_id:'p',errors:1,warnings:0,checked_artifacts:1,issues:[{code:'INVALID_POINTER',severity:'error',location:'Text <unsafe>',offset:4,remedy:'Choose the correct pointer base.'}]}};
const ctx={state,use:()=>{}};const html=projectChecks(ctx);assert.match(html,/Choose the correct pointer base/);assert.match(html,/0x4/);assert.ok(!html.includes('<unsafe>'));
state.project={project_id:'other'};assert.ok(!projectChecks(ctx).includes('INVALID_POINTER'));
state.supportPreview={selection:'p',report:{checks:[]}};assert.ok(!supportControls(ctx).includes('Download report'));
console.log('Project checks show locations/remedies and hide results from a different project.');
