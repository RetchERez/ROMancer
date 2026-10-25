import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../romancer/ui/startup.js',import.meta.url),'utf8');
let deadline,recoveries=0,ack=0;const listeners={};
const root={dataset:{},replaceChildren(){recoveries++;}};
const context={URL,URLSearchParams,location:{href:'http://127.0.0.1/?launch='+'a'.repeat(32)+'#token=fixture'},setTimeout(fn){deadline=fn;},clearTimeout(){},window:{addEventListener(name,fn){listeners[name]=fn;}},
 document:{head:{append(){}},querySelector(){return {className:'shell'};},getElementById(){return root;},createElement(){return {append(){}};}},fetch:async()=>ack++};
vm.runInNewContext(source,context);deadline();assert.equal(recoveries,1,'An unfinished shell must not suppress startup recovery');
await listeners['romancer-ready']();assert.equal(ack,0,'A late ready event must not acknowledge recovered startup');assert.equal(root.dataset.startupRecovered,'true');
console.log('Unfinished shell reaches recovery; late ready event cannot claim readiness.');
