import {button,esc} from './common.js';
export const OVERVIEW_TASKS=[
 ['assets','Graphics & fonts','Tiles, sprites and palettes'],
 ['scripts','Text & layout','Text, fonts and dialogue'],
 ['tables','Numbers & stats','Editable tables and values'],
 ['levels','Levels','Rooms, objects and terrain'],
 ['sound','Music & sound','Samples and known sequences'],
 ['debug','Investigation','Find values and source bytes'],
 ['playtest','Playtest','Play, step and save states'],
 ['release','Export & patches','Apply or export patches']
];
export function overviewTasks(){return `<section class="card"><div class="card-heading"><h3>Choose a task</h3></div><div class="overview-tasks">${OVERVIEW_TASKS.map(([id,label,note])=>`<div>${button(label,'navigate',{id,icon:id})}<p class="subtle">${esc(note)}</p></div>`).join('')}</div></section>`;}
