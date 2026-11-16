import {button,esc} from './common.js';
export const OVERVIEW_TASKS=[
 ['assets','Graphics & fonts','Tiles, sprites and palettes'],
 ['scripts','Text & layout','Text, fonts and dialogue'],
 ['tables','Numbers & stats','Editable tables and values'],
 ['sound','Music & sound','Samples and known sequences'],
 ['resources','Inspect ROM bytes','Search bytes and compare files'],
 ['debug','Investigation','Find changing values and trace access'],
 ['playtest','Playtest','Play, step and save states'],
 ['release','Export & patches','Apply or export patches']
];
export function overviewTasks(hasReadiness=false){const tasks=hasReadiness?OVERVIEW_TASKS.slice(4):OVERVIEW_TASKS;return `<section class="card"><div class="card-heading"><h3>${hasReadiness?'Inspect, test and share':'What do you want to change?'}</h3></div><div class="overview-tasks">${tasks.map(([id,label,note])=>`<div>${button(label,'navigate',{id,icon:id})}<p class="subtle">${esc(note)}</p></div>`).join('')}</div></section>`;}
