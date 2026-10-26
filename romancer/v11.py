from __future__ import annotations

from pathlib import Path
from typing import Any
from .util import write_json
from .live_debug_v11 import DebugBridgeClient, FixtureDebugBridge, bridge_probe, mgba_bridge_template
from .address_translate_v11 import translate_address

VERSION="11.0.0"


def add_v11_parsers(sub)->None:
    s=sub.add_parser("live-debug-probe",help="[v11] Probe a ROMancer live-debug bridge")
    s.add_argument("--host",default="127.0.0.1"); s.add_argument("--port",type=int,default=17680); s.add_argument("--timeout",type=float,default=3); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("address-translate",help="[v11] Translate a verified CPU/bus address to a ROM file offset when mapping is defined")
    s.add_argument("--system",required=True); s.add_argument("--addr",required=True); s.add_argument("--mapping"); s.add_argument("--headered",action="store_true"); s.add_argument("--rom-size",type=lambda x:int(x,0)); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("mgba-bridge-template",help="[v11] Emit a conservative mGBA Lua bridge bootstrap based on documented socket/debug APIs")
    s.add_argument("--port",type=int,default=17680); s.add_argument("--out"); s.add_argument("--json",action="store_true")
    s=sub.add_parser("v11-self-test",help="[v11] Test live bridge transport and address translators")
    s.add_argument("--out"); s.add_argument("--json",action="store_true")


def v11_self_test(out:str|None=None)->dict[str,Any]:
    tests=[]
    server=FixtureDebugBridge(); port=server.start()
    try:
        c=DebugBridgeClient(port=port); hello=c.connect(); c.watchpoint(0x2000); stop=c.run_until_stop(); mem=c.read_memory(0x2000); c.close()
        tests.append({"name":"live JSON debug transport","ok":hello.get("live") is True and stop.get("reason")=="watchpoint" and mem.get("data")==[5]})
    finally: server.stop()
    g=translate_address("gba","0x08000120",rom_size=0x200000)
    tests.append({"name":"GBA bus to ROM translation","ok":g.get("resolved") and g.get("rom_offset")=="0x00000120","detail":g})
    s=translate_address("snes","C2:8000",mapping="lorom")
    tests.append({"name":"SNES mapping translation","ok":s.get("resolved") is True and s.get("rom_offset_headerless")=="0x210000","detail":s})
    n=translate_address("nes","0x8000")
    tests.append({"name":"bank-dependent mapping refusal","ok":n.get("resolved") is False})
    ok=all(t["ok"] for t in tests)
    result={"tool":"ROMancer","version":VERSION,"feature":"v11 self-test","ok":ok,"tests":tests}
    if out: write_json(out,result)
    return result


def dispatch_v11(args):
    c=getattr(args,"cmd","")
    if c=="live-debug-probe":
        r=bridge_probe(args.host,args.port,args.timeout); write_json(args.out,r) if args.out else None; return True,r
    if c=="address-translate":
        r=translate_address(args.system,args.addr,mapping=args.mapping,headered=args.headered,rom_size=args.rom_size); write_json(args.out,r) if args.out else None; return True,r
    if c=="mgba-bridge-template":
        text=mgba_bridge_template(args.port)
        if args.out: Path(args.out).write_text(text,encoding="utf-8")
        return True,{"tool":"ROMancer","version":VERSION,"feature":"mGBA bridge template","out":args.out,"text":text}
    if c=="v11-self-test": return True,v11_self_test(args.out)
    return False,None
