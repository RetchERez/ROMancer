import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const tests=fs.readdirSync(path.join(root,'tests')).filter(n=>/^ui_.*\.mjs$/.test(n)).sort();
if(!tests.length)throw Error('No UI regression suites were found.');
for(const test of tests){
 console.log(`\n${test}`);
 const result=spawnSync(process.execPath,[path.join(root,'tests',test)],{cwd:root,stdio:'inherit'});
 if(result.error)throw result.error;
 if(result.status!==0)process.exit(result.status||1);
}
console.log(`\n${tests.length} UI suites passed.`);
