-- Original bounded observer. Never returns replacement bus data or writes memory.
local output=assert(io.open('trace.tsv','wb'))
local cpu=assert(manager.machine.devices[':maincpu'])
local space=assert(cpu.spaces['program'])
local symbols=emu.symbol_table(cpu)
local debugger=assert(manager.machine.debugger)
local pad=assert(manager.machine.ioport.ports[':ctrl1:mdpad:PAD'])
local steps=@STEPS@
local probes=@PROBES@
local frame,emitted,omitted,observer_depth=0,0,0,0
local finished,trace_started=false,false
local masks={up=1,down=2,left=4,right=8,b=16,c=32,a=64,start=128}
local fields={}
for name,mask in pairs(masks) do fields[name]=assert(pad:field(mask)) end
local function input()
 local remaining=frame
 local selected=steps[#steps]
 for _,step in ipairs(steps) do
  if remaining<step.frames then selected=step;break end
  remaining=remaining-step.frames
 end
 for name,field in pairs(fields) do field:set_value(selected.buttons[name] and 1 or 0) end
end
local function window(pc)
 if pc<0 or pc>0xfffff0 or emitted>16 then return '-' end
 observer_depth=observer_depth+1
 local ok,value=pcall(function()
  local bytes={}
  for i=0,15 do bytes[#bytes+1]=string.format('%02x',symbols:memory_value(nil,'p',pc+i,1,true)) end
  return table.concat(bytes)
 end)
 observer_depth=observer_depth-1
 if not ok then return '-' end
 return value
end
local function matches(kind,address)
 for _,probe in ipairs(probes) do
  if probe.kind==kind then
   local physical=probe.domain=='genesisWorkRam'
   local value=physical and (address&0xffff) or address
   if (not physical or address>=0xe00000) and value>=probe.start and value<=probe.finish then return true end
  end
 end
 return false
end
local taps={}
for _,kind in ipairs({'read','write'}) do
 local low,high=nil,nil
 for _,probe in ipairs(probes) do
  if probe.kind==kind then
   local first=probe.domain=='genesisWorkRam' and 0xe00000 or probe.start
   local last=probe.domain=='genesisWorkRam' and 0xffffff or probe.finish
   low=low and math.min(low,first) or first;high=high and math.max(high,last) or last
  end
 end
 if low then
  local function callback(address,data,mask)
   if observer_depth>0 or manager.machine:side_effects_disabled() then return end
   if finished or frame<@START_FRAME@ then return end
   for lane=0,1 do
    local shift=lane==0 and 8 or 0
    local byte_address=address+lane
    if ((mask>>shift)&255)~=0 and matches(kind,byte_address) then
     if emitted>=@EVENT_LIMIT@ then omitted=omitted+1
     else
      emitted=emitted+1
      local pc=cpu.state['CURPC'].value
      local value=(data>>shift)&255
      output:write(string.format('E\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n',emitted,kind,byte_address,value,pc,frame,address,data,mask,window(pc)))
      if emitted<=16 then
       for _,name in ipairs({'CURPC','PC','SR','D0','D1','D2','D3','D4','D5','D6','D7','A0','A1','A2','A3','A4','A5','A6','A7'}) do
        if cpu.state[name] then output:write(string.format('R\t%d\t%s\t%.0f\n',emitted,name,cpu.state[name].value)) end
       end
      end
     end
    end
   end
  end
  if kind=='read' then taps[#taps+1]=space:install_read_tap(low&0xfffffe,high|1,'romancer_reads',callback)
  else taps[#taps+1]=space:install_write_tap(low&0xfffffe,high|1,'romancer_writes',callback) end
 end
end
local function trace()
 if trace_started then return end
 trace_started=true;debugger.visible_cpu=cpu
 debugger:command('do temp0=0')
 -- Stop from a registerpoint after the trace action; never delete a running tracer.
 debugger:command('rpset temp0>=#@TRACE_LIMIT@,{trace off,:maincpu;rpdisable;g}')
 debugger:command('trace "instructions.log",:maincpu,noloop,{do temp0=temp0+1;tracelog "EXEC n=%d curpc=%06X pc=%06X\\n",temp0,curpc,pc}')
end
output:write('BEGIN\t1\t@NONCE@\tgenesis\n');output:flush();input()
if @START_FRAME@==0 then trace() end
_G.romancer_frames=emu.add_machine_frame_notifier(function()
 frame=frame+1
 if frame>=@FRAMES@ then
  finished=true
  if trace_started then debugger:command('trace off,:maincpu') end
  for _,field in pairs(fields) do field:clear_value() end
  output:write(string.format('END\t%d\t%d\t%d\n',frame,emitted,omitted));output:close();manager.machine:exit()
 else
  input();if frame>=@START_FRAME@ then trace() end
  output:flush()
 end
end)
