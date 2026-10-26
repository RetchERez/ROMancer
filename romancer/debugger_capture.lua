-- Original ROMancer observational adapter. The backend retains its own license.
local cpu=emu.cpuType.@CPU@
local memory=emu.memType.@MEMORY@
local steps=@STEPS@
local probes=@PROBES@
local output=assert(io.open("trace.tsv","w"))
local frames=0
local emitted=0
local omitted=0
local executed=0
local done=false
local lastExec=-1
local lastDomain=-1
local lastPhysical=-1
output:write("BEGIN\t1\t@NONCE@\t@SYSTEM@\n")
for _,name in ipairs({"nesPrgRom","nesChrRom","nesInternalRam","snesPrgRom","snesWorkRam","gbPrgRom","gbWorkRam","gbaPrgRom","gbaExtWorkRam","gbaIntWorkRam"}) do
 local value=emu.memType[name]
 if value~=nil then output:write("DOMAIN\t"..name.."\t"..value.."\n") end
end
local function finish(reason)
 if done then return end
 done=true
 output:write("END\t"..frames.."\t"..emitted.."\t"..omitted.."\t"..executed.."\t"..reason.."\n")
 output:flush();output:close();emu.stop(0)
end
emu.addMemoryCallback(function(address,value)
 if done then return end
 lastExec=address
 local mapped=emu.convertAddress(address,memory,cpu)
 lastDomain=mapped and mapped.memType or -1
 lastPhysical=mapped and mapped.address or -1
 executed=executed+1
 if executed>=@INSTRUCTION_LIMIT@ then finish("instruction_limit") end
end,emu.callbackType.exec,0,@MAX_ADDRESS@,cpu,memory)
local registerNames={"pc","sp","a","x","y","ps","k","dbr","d","flags","b","c","e","h","l","emulationMode",
 "r0","r1","r2","r3","r4","r5","r6","r7","r8","r9","r10","r11","r12","r13","r14","r15",
 "cpsr.thumb","pipeline.execute.address","pipeline.execute.opCode"}
local function record(kind,address,value)
 if done then return end
 if frames<@START_FRAME@ then return end
 if emitted>=@EVENT_LIMIT@ then omitted=omitted+1;return end
 emitted=emitted+1
 local mapping=emu.convertAddress(address,memory,cpu)
 local state=emu.getState()
 output:write(string.format("E\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",emitted,kind,address,value,lastExec,
  mapping and mapping.memType or -1,mapping and mapping.address or -1,lastDomain,lastPhysical,state.frameCount))
 if emitted<=16 then
  local registers=emu.getCpuState(cpu)
  for _,name in ipairs(registerNames) do
   local v=registers[name]
   if type(v)=="number" then output:write("R\t"..emitted.."\t"..name.."\tn\t"..string.format("%.0f",v).."\n")
   elseif type(v)=="boolean" then output:write("R\t"..emitted.."\t"..name.."\tb\t"..tostring(v).."\n") end
  end
 end
end
for _,probe in ipairs(probes) do
 local kind=probe.kind
 local probeMemory=probe.domain and assert(emu.memType[probe.domain]) or memory
 emu.addMemoryCallback(function(a,v) record(kind,a,v) end,emu.callbackType[kind],probe.start,probe.finish,cpu,probeMemory)
end
emu.addEventCallback(function()
 if done then return end
 local elapsed=0
 for _,step in ipairs(steps) do
  elapsed=elapsed+step.frames
  if frames<elapsed then emu.setInput(step.buttons,0);return end
 end
end,emu.eventType.inputPolled)
emu.addEventCallback(function()
 if done then return end
 frames=frames+1
 if frames>=@FRAMES@ then finish("frames") end
end,emu.eventType.endFrame)
