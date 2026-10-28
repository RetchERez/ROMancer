export function selectionTicket(state){state.selectionRevision=(state.selectionRevision||0)+1;return state.selectionRevision;}
export function selectionCurrent(state,ticket){return state.selectionRevision===ticket;}
export function releaseProjectResources(state){
 clearTimeout(state.buildCheckTimer);state.buildCheckTimer=null;state.connectedPage=0;
 state.gameVisualModel=null;state.animationClock?.stop();state.animationClock=null;state.animationPlaying=false;state.animationIndex=0;state.valueSearch=null;state.valueVideo=null;state.soundPlayer?.close();state.soundPlayer=null;state.soundPreview=null;
 for(const key of ['openAnimationAfterMount','definitionReview','commandDefinitionReview','commandFocus','animationSaveReview','connectedAnimation','connectedSoundJump','compressedReferenceSurvey','soundInstrument','visualSourceProof','verifiedVisualSource','savedGameplayTrace','connectedNode','connectedTraceFocus','connectedAssetSetup','connectedTableJump','connectedLevelJump','buildCheckView','buildCheckReport','tablePreview','dataRelocation','nativeSourceContext','structuralLab','structuralPrefill','tableProposal','nativeTrace','nativeProbe','investigationSeries','gameMapsView','gameMapEditor','levelEditor','levelClipboard','levelRect','paint','pixelHistories','pixelHistoryScope','spriteHistory','hexDraft','hexReview','hexSearch','hexNumbers','hexExplanation','hexBookmarks','hexComparison','historyComparison','translationSheet','translationReview'])state[key]=null;
 state.drafts={};state.romScans={};state.graphicsInvestigations={};state.graphicsPartHeight=null;state.graphicsRegionOpen=false;state.results={};
}
export function clearProjectState(state){
 selectionTicket(state);
 releaseProjectResources(state);
 for(const key of ['project','artifact','runtime','frame','snapshot','pending','paint','profileFamily','profileLoadedFamily','candidateReview','resourcePrefill','openDeclaration'])state[key]=null;
 state.results={};state.playing=false;state.heldButtons=[];state.page='overview';
 state.scriptPage=0;state.assetPage=0;state.catalogPage=0;state.catalogQuery='';
}
export function droppedSource(files){
 if(!files||files.length!==1)throw new Error('Drop one file at a time.');
 const file=files[0];if(!Number.isSafeInteger(file.size)||file.size<1)throw new Error('The selected file is empty. Choose a ROM file.');
 if(file.size>64*1024*1024)throw new Error('Files larger than64 MiB need Advanced path import.');
 return file;
}
export function helpForError(message){
 const text=String(message).toLowerCase();
 if(/old.byte|precondition/.test(text))return {topic:'discovery',label:'Check source bytes'};
 if(/core|bios|playtest|native|architecture/.test(text))return {topic:'playtest',label:'Playtest setup help'};
 if(/stale|revision|changed|lock|draft|backup|restore/.test(text))return {topic:'recovery',label:'Recovery help'};
 if(/text|slot|encoding|terminator|control|overflow/.test(text))return {topic:'text',label:'Text editing help'};
 if(/table|record|numeric|stride|integer/.test(text))return {topic:'tables',label:'Data table help'};
 if(/palette|pixel|tile|graphic|glyph/.test(text))return {topic:'graphics',label:'Graphics help'};
 if(/compression|lz10|rle|allocation/.test(text))return {topic:'compression',label:'Compression help'};
 if(/patch|bps|export/.test(text))return {topic:'export',label:'Patch export help'};
 return {topic:'start',label:'Open help'};
}

export class DraftQueue {
 constructor(onChange=()=>{}){this.pending=new Map();this.failed=new Map();this.operations=new Map();this.onChange=onChange;}
 snapshot(){return {pending:this.pending.size,failed:this.failed.size,state:this.failed.size?'failed':this.pending.size?'saving':'saved',unsafe:!!(this.pending.size||this.failed.size)};}
 changed(){try{this.onChange(this.snapshot());}catch{}}
 enqueue(key,operation,onError){
  this.operations.set(key,{operation,onError});
  const prior=this.pending.get(key)||Promise.resolve();
  const next=prior.then(operation).then(()=>this.failed.delete(key)).catch(error=>{this.failed.set(key,error);try{onError(error);}catch{}});
  this.pending.set(key,next);
  this.changed();
  void next.finally(()=>{if(this.pending.get(key)===next){this.pending.delete(key);if(!this.failed.has(key))this.operations.delete(key);}this.changed();});
 }
 async retry(){for(const key of this.failed.keys())if(!this.pending.has(key)){const task=this.operations.get(key);if(task)this.enqueue(key,task.operation,task.onError);}await this.flush();}
 async flush(){while(this.pending.size)await Promise.all([...this.pending.values()]);if(this.failed.size)throw Error('Draft not saved. Your unsaved edits are still here. Retry saving before changing source or project.');}
 clear(){if(this.pending.size||this.failed.size)throw Error('Unsaved edits must be saved before clearing drafts.');this.failed.clear();this.operations.clear();this.changed();}
}
