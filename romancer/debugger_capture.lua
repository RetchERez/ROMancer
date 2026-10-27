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
local perProbe=math.max(1,math.floor(@EVENT_LIMIT@/#probes))
local lastExec=-1
local lastDomain=-1
local lastPhysical=-1
output:write("BEGIN\t1\t@NONCE@\t@SYSTEM@\n")
for _,name in ipairs({"nesPrgRom","nesChrRom","nesChrRam","nesInternalRam","nesSpriteRam","nesPaletteRam","nesNametableRam","snesPrgRom","snesWorkRam","snesVideoRam","snesSpriteRam","snesCgRam","gbPrgRom","gbWorkRam","gbVideoRam","gbSpriteRam","gbBgPaletteRam","gbObjPaletteRam","gbaPrgRom","gbaExtWorkRam","gbaIntWorkRam","gbaVideoRam","gbaSpriteRam","gbaPaletteRam","smsPrgRom","smsWorkRam","smsVideoRam","smsPaletteRam"}) do
 local value=emu.memType[name]
 if value~=nil then output:write("DOMAIN\t"..name.."\t"..value.."\n") end
end
local function graphicsSnapshot()
 if not @GRAPHICS_SNAPSHOT@ then return end
 for _,domain in ipairs(@SNAPSHOT_DOMAINS@) do
  local memoryType=emu.memType[domain.name]
  if memoryType then
   local size=math.min(domain.size,emu.getMemorySize(memoryType));local bytes={}
   for i=0,size-1 do bytes[#bytes+1]=string.format('%02x',emu.read(i,memoryType+0x100)) end
   if size>0 then output:write('M\t'..domain.name..'\t'..size..'\t'..table.concat(bytes)..'\n') end
  end
 end
 local state=emu.getState();local names={}
 for name,value in pairs(state) do
  local lower=string.lower(name)
  if (string.find(lower,'ppu') or string.find(lower,'vdp')) and string.match(name,'^[%a][%w_.%[%]]*$') and #name<=128 and
     (type(value)=='boolean' or type(value)=='number' and value==math.floor(value) and math.abs(value)<4503599627370496) then names[#names+1]=name end
 end
 table.sort(names)
 for i=1,math.min(512,#names) do
  local name=names[i];local value=state[name]
  output:write('S\t'..name..'\t'..(type(value)=='boolean' and 'b' or 'n')..'\t'..tostring(value)..'\n')
 end
 local size=emu.getScreenSize();local pixels=emu.getScreenBuffer();local bytes={}
 assert(size.width*size.height==#pixels and #pixels<=262144)
 for _,color in ipairs(pixels) do bytes[#bytes+1]=string.format('%06x',color) end
 output:write('SCREEN\t'..size.width..'\t'..size.height..'\t'..table.concat(bytes)..'\n')
end
local function finish(reason)
 if done then return end
 done=true
 graphicsSnapshot()
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
local physicalVideo={snesVideoRam=true,snesSpriteRam=true,snesCgRam=true,nesSpriteRam=true,smsVideoRam=true,smsPaletteRam=true}
local function observedMapping(address,probe,access)
 if access then return {memType=access.memoryType,address=access.physicalAddress} end
 local domain=probe.domain
 if physicalVideo[domain] then return {memType=emu.memType[domain],address=address} end
 if domain=="nesChrRom" or domain=="nesChrRam" or domain=="nesPaletteRam" or domain=="nesNametableRam" then return emu.convertAddress(address,emu.memType.nesPpuMemory,cpu) end
 -- GB/GBA CPU video accesses use bus addresses; PPU callbacks use physical indices.
 if domain=="gbVideoRam" and address<0x8000 or domain=="gbSpriteRam" and address<0xfe00 or
    domain=="gbBgPaletteRam" or domain=="gbObjPaletteRam" or
    (domain=="gbaVideoRam" or domain=="gbaSpriteRam" or domain=="gbaPaletteRam") and address<0x02000000 then
  return {memType=emu.memType[domain],address=address}
 end
 return emu.convertAddress(address,memory,cpu)
end
local function record(kind,address,value,probe,access)
 if done then return end
 if frames<@START_FRAME@ then return end
 if emitted>=@EVENT_LIMIT@ or (probe.emitted or 0)>=perProbe then omitted=omitted+1;return end
 probe.emitted=(probe.emitted or 0)+1
 emitted=emitted+1
 local mapping=observedMapping(address,probe,access)
 local state=emu.getState()
 output:write(string.format("E\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",emitted,kind,address,value,lastExec,
  mapping and mapping.memType or -1,mapping and mapping.address or -1,lastDomain,lastPhysical,state.frameCount))
 if access then output:write(string.format('N\t%d\t%s\t%d\t%d\t%d\n',emitted,access.operation,access.valueBytes,access.memoryType,access.physicalAddress)) end
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
 emu.addMemoryCallback(function(a,v,access) record(kind,a,v,probe,access) end,emu.callbackType[kind],probe.start,probe.finish,cpu,probeMemory)
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
