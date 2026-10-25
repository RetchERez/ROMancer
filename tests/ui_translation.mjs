import assert from 'node:assert/strict';
import {translationControls,translationPreview} from '../romancer/ui/translation_controls.js';
const state={project:{project_id:'p'},artifact:{artifact_id:'a',sha256:'s'}};
const doc={ok:true,write_supported:true,document_id:'doc',schema_sha256:'schema'};
state.translationSheet={scope:'p:a:s',preview:{status:"CHECK_TRANSLATIONS",valid:false,document_id:'doc',schema_sha256:'schema',changed_segments:1,issues:[{record_id:'a',code:'CAPACITY',message:'Shorten the text.'}],previews:[{record_id:'a',used_bytes:20,capacity:12,before:['A'],after:['<unsafe>']} ]}};
const ctx={state,use:()=>{},draft:(_k,f)=>f};let html=translationControls(ctx,doc);assert.match(html,/Shorten the text/);assert.match(html,/20 \/ 12/);assert.ok(!html.includes('<unsafe>'));
assert.equal(translationPreview(state,{...doc,document_id:'new'}),null);state.artifact.sha256='new';assert.equal(translationPreview(state,doc),null);
console.log('Translation previews show byte overflow and never follow a changed source or document.');
