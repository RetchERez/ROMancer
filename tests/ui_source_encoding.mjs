import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../romancer/ui');
for(const name of fs.readdirSync(root,{recursive:true}).filter(n=>n.endsWith('.js'))){
 const text=new TextDecoder('utf-8',{fatal:true}).decode(fs.readFileSync(path.join(root,name)));
 assert.doesNotMatch(text,/\u00c2[\u0080-\u00bf]|\u00e2[\u0080-\u00bf\u20ac\u2020\u0153]/,`${name} contains misdecoded UI punctuation.`);
}
console.log('UI sources and generated bundle retain readable UTF-8 punctuation.');
