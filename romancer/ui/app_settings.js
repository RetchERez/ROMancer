import {readPreference,writePreference} from './preferences.js';
import {applyInterfaceScale} from './interface_scale.js';

export const DEFAULT_SETTINGS=Object.freeze({theme:'romancer',scale:100,autoDeepScan:true,autoGraphics:true,rememberWorkspace:true,volume:80,startMuted:false,loopPreview:false,reduceMotion:false,advancedTools:false});
const keys=Object.keys(DEFAULT_SETTINGS),booleanKeys=keys.filter(key=>typeof DEFAULT_SETTINGS[key]==='boolean');
export function validateSettings(values){
 if(!values||typeof values!=='object'||Array.isArray(values)||Object.keys(values).length!==keys.length||Object.keys(values).some(key=>!keys.includes(key)))throw Error('Settings contain missing or unknown fields.');
 if(!['romancer','dark','light'].includes(values.theme))throw Error('Choose a valid theme.');
 if(!Number.isSafeInteger(values.scale)||![100,125,150,200].includes(values.scale))throw Error('Choose a supported interface scale.');
 if(!Number.isSafeInteger(values.volume)||values.volume<0||values.volume>100)throw Error('Volume must be a whole number from 0 to 100.');
 for(const key of booleanKeys)if(typeof values[key]!=='boolean')throw Error(key+' must be true or false.');
 return Object.fromEntries(keys.map(key=>[key,values[key]]));
}
function checkedPacket(packet){
 if(!packet||packet.ok===false||!Number.isSafeInteger(packet.revision)||packet.revision<0)throw Error(packet?.error?.message||packet?.error||'Settings response has an invalid revision.');
 return {revision:packet.revision,values:validateSettings(packet.values)};
}
let cached={revision:0,values:{...DEFAULT_SETTINGS}},cacheVersion=0;
try{const saved=readPreference('romancer-settings');if(saved)cached=checkedPacket(JSON.parse(saved));else{const scale=Number(readPreference('romancer-scale',100));if([100,125,150,200].includes(scale))cached.values.scale=scale;}}catch{/* Invalid local caches never prevent startup. The workspace remains authoritative. */}

export function getSettings(){return {...cached.values};}
export function settingsAppearance(values=getSettings()){
 const next=validateSettings(values),root=globalThis.document?.documentElement;
 if(root){root.dataset.theme=next.theme;root.classList.toggle('reduce-motion',next.reduceMotion);if(globalThis.window)applyInterfaceScale(next.scale);}
 return next;
}
export function hydrateSettings(packet){
 const next=checkedPacket(packet);settingsAppearance(next.values);cached=next;cacheVersion++;
 writePreference('romancer-settings',JSON.stringify(next));writePreference('romancer-scale',String(next.values.scale));return getSettings();
}
export async function loadSettings(api){
 const version=cacheVersion,packet=checkedPacket(await api.call('settings.get',{}));
 // An older startup response must not roll back settings applied in the meantime.
 if(cacheVersion===version||packet.revision>cached.revision)return hydrateSettings(packet);return getSettings();
}
export async function saveSettings(api,values){
 const next=validateSettings(values),revision=cached.revision,packet=checkedPacket(await api.call('settings.save',{revision,values:next}));
 if(packet.revision!==revision+1||JSON.stringify(packet.values)!==JSON.stringify(next))throw Error('Settings save returned different values. Reopen Settings to reload them.');
 if(packet.revision>=cached.revision)return hydrateSettings(packet);return getSettings();
}
