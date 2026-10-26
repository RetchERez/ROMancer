function merged(rows){const output=[];for(const row of rows.sort((a,b)=>a[0]-b[0])){const last=output.at(-1);if(last&&row[0]<=last[1])last[1]=Math.max(last[1],row[1]);else output.push([...row]);}return output;}
export function changeSummary(result){
 if(!result?.ok||!(result.workbench_plan_id||result.plan_id))return null;
 const primary=result.hunks||result.edits;if(!Array.isArray(primary)||!primary.length)return null;
 const changed=[],integrity=[];let budget=0;
 for(const [rows,isIntegrity] of [[primary,false],[result.integrity_edits||[],true]]){
  if(!Array.isArray(rows))return null;
  for(const row of rows){
   const before=row.before_hex??row.before,after=row.after_hex??row.after;
   if(!Number.isSafeInteger(row.offset)||row.offset<0||typeof before!=='string'||typeof after!=='string'||before.length!==after.length||before.length%2||!/^[a-f\d]*$/i.test(before+after))return null;
   budget+=before.length/2;if(budget>4*1024*1024)return null;
   let start=null;
   for(let i=0;i<=before.length;i+=2){const differs=i<before.length&&before.slice(i,i+2).toLowerCase()!==after.slice(i,i+2).toLowerCase();if(differs&&start===null)start=row.offset+i/2;if(!differs&&start!==null){const range=[start,row.offset+i/2];changed.push(range);if(isIntegrity)integrity.push(range);start=null;if(changed.length>65536)return null;}}
  }
 }
 const union=merged(changed);return {changedBytes:union.reduce((n,r)=>n+r[1]-r[0],0),ranges:union.length,integrityBytes:merged(integrity).reduce((n,r)=>n+r[1]-r[0],0)};
}
export function summaryText(result){const value=changeSummary(result);return value?`${value.changedBytes} byte${value.changedBytes===1?'':'s'} changed across ${value.ranges} range${value.ranges===1?'':'s'}${value.integrityBytes?` · includes ${value.integrityBytes} checksum/header byte${value.integrityBytes===1?'':'s'}`:''}. A separate build preserves the original.`:'';}
