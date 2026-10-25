// App-local commands only. No registration of operating-system hotkeys.
export const SHORTCUTS=[['Ctrl+S','Save drafts now'],['Ctrl+Z','Undo the active editor'],['Ctrl+Y / Ctrl+Shift+Z','Redo the active editor'],['Ctrl+K','Search the workspace'],['?','Show keyboard shortcuts']];
export function shortcutFor(event,{modalOpen=false,gameFocused=false}={}){
 if(event.defaultPrevented||event.repeat||event.isComposing||event.keyCode===229||event.metaKey||event.altKey||modalOpen||gameFocused)return null;
 const editing=!!event.target?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"])'),key=event.key.toLowerCase();
 if(event.ctrlKey){
  if(!event.shiftKey&&key==='s')return 'save';
  if(!event.shiftKey&&key==='k')return 'search';
  if(editing)return null;
  if(key==='z')return event.shiftKey?'redo':'undo';
  if(!event.shiftKey&&key==='y')return 'redo';
 }else if(!editing&&event.key==='?')return 'help';
 return null;
}
export function historyAction(page,editor,direction,available){
 const suffix=direction<0?'undo':'redo';
 const prefix=page==='levels'&&editor==='level-canvas'?'levels':page==='assets'?(editor==='sprite-canvas'?'sprite':editor==='paint-canvas'?'pixel':null):null;
 const action=prefix&&prefix+'-'+suffix;
 return action&&available(action)?action:'draft-'+suffix;
}
export function rememberEditor(state,event,refresh){const canvas=event.target.closest?.('canvas');if(canvas)state.historyEditor=canvas.id;else if(event.target.closest?.('input,textarea,select,[contenteditable]'))state.historyEditor='field';else return;refresh();}
