// Development only: npm install --prefix <tools> esbuild@0.25.12
// node tools/build_ui.mjs <tools>/node_modules/esbuild/lib/main.js
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const library=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'node_modules/esbuild/lib/main.js');
const esbuild=(await import(pathToFileURL(library).href)).default;
if(esbuild.version!=='0.25.12')throw Error('Use esbuild@0.25.12 for the checked release bundle.');
const result=await esbuild.build({absWorkingDir:root,entryPoints:['romancer/ui/desktop_entry.js'],bundle:true,
 outfile:'romancer/ui/app.bundle.js',format:'iife',platform:'browser',target:['chrome89','firefox89'],metafile:true,
 charset:'utf8',legalComments:'none',logLevel:'warning'});
if(Object.values(result.metafile.outputs).some(o=>o.imports.length))throw Error('The desktop bundle must have no external imports.');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const sources=Object.fromEntries(Object.keys(result.metafile.inputs).sort().map(name=>[name,sha(fs.readFileSync(path.join(root,name)))]));
fs.writeFileSync(path.join(root,'romancer/ui/bundle.json'),JSON.stringify({schema_version:1,builder:'esbuild@0.25.12',sources,sha256:sha(fs.readFileSync(path.join(root,'romancer/ui/app.bundle.js')))},null,2)+'\n');
console.log(`Built desktop UI from ${Object.keys(sources).length} local modules.`);
