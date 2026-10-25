import assert from 'node:assert/strict';
import test from 'node:test';

test('denied session storage keeps launch authentication usable',async()=>{
 globalThis.location={hash:'#token=local-fixture',pathname:'/'};
 globalThis.history={replaceState(){throw Error('token must remain when storage fails');}};
 Object.defineProperty(globalThis,'sessionStorage',{configurable:true,get(){throw Error('storage denied');}});
 globalThis.fetch=async(_url,options)=>({ok:true,json:async()=>({ok:options.headers.Authorization==='Bearer local-fixture'})});
 const {api}=await import('../romancer/ui/api.js?denied');
 assert.equal((await api.call('system.capabilities')).ok,true);
});

test('optional local preferences work when browser storage is denied',async()=>{
 Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw Error('storage denied');}});
 const p=await import('../romancer/ui/preferences.js');
 assert.equal(p.readPreference('missing',100),100);
 p.writePreference('size','125');assert.equal(p.readPreference('size'),'125');
 p.removePreference('size');assert.equal(p.readPreference('size'),null);
});

for(const phase of ['fetch','body'])test('an unresponsive '+phase+' has a usable deadline',async()=>{
 globalThis.location={hash:'#token=local-fixture',pathname:'/'};
 Object.defineProperty(globalThis,'sessionStorage',{configurable:true,writable:true,value:{getItem(){return null;},setItem(){}}});globalThis.history={replaceState(){}};
 const {api}=await import('../romancer/ui/api.js?'+phase);
 const realTimer=globalThis.setTimeout;globalThis.setTimeout=(fn)=>realTimer(fn,1);
 globalThis.fetch=phase==='fetch'?()=>new Promise(()=>{}):async()=>({ok:true,json:()=>new Promise(()=>{})});
 try {await assert.rejects(Promise.race([api.call('system.capabilities'),new Promise((_,reject)=>realTimer(()=>reject(Error('missing deadline')),500))]),/did not respond in time/);}
 finally{globalThis.setTimeout=realTimer;}
});
