// Appearance/history are optional. Storage restrictions must not prevent startup.
const memory=new Map();
export function readPreference(key,fallback=null){try{return localStorage.getItem(key)??memory.get(key)??fallback;}catch{return memory.get(key)??fallback;}}
export function writePreference(key,value){memory.set(key,String(value));try{localStorage.setItem(key,String(value));}catch{}}
export function removePreference(key){memory.delete(key);try{localStorage.removeItem(key);}catch{}}
