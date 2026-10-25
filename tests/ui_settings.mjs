import assert from 'node:assert/strict';
import {render} from '../romancer/ui/views/settings.js';
const capabilities=Object.fromEntries(['identification','raw_inspection','structured_formats','automatic_resource_discovery'].map(k=>[k,{status:'supported',reason:'Known layout.'}]));
const packs=['nes','snes','gba'].map(id=>({id,label:id,release_focus:true,formats:['linear'],capabilities}));
const handlers={},state={capabilities:{systems:{systems:packs},version:'1.0.2'}};
const ctx={state,api:{call:async(op,p)=>op==='profiles.get'?{profile:p.system_id==='nes'?null:{core:'local'}}:p.system_id==='snes'?{ok:true}:Promise.reject(Error('Core changed'))},use:h=>Object.assign(handlers,h),draft:(_k,v)=>v};
const html=await render(ctx);assert.ok(html.includes('Choose core'));assert.ok(html.includes('Ready'));assert.ok(html.includes('Needs attention'));assert.ok(!html.includes('>Missing<'));
console.log('Settings separates absent setup, verified inputs and a changed core; setup actions remain available.');
