import {startup,startupReady} from './app.js';
startup.then(()=>window.dispatchEvent(new Event(startupReady?'romancer-ready':'romancer-startup-error')))
 .catch(()=>window.dispatchEvent(new Event('romancer-startup-error')));
