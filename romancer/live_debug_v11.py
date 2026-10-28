from __future__ import annotations

"""ROMancer v11 live debugger bridge protocol.

The bridge is newline-delimited JSON over TCP. ROMancer can control any backend
that implements this small protocol. The protocol is intentionally backend-
neutral; individual emulator-side bridges must expose only capabilities that
the emulator truly supports.
"""

import json, socket, threading
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = 1


class DebugBridgeError(RuntimeError):
    pass


@dataclass
class DebugBridgeClient:
    host: str = "127.0.0.1"
    port: int = 17680
    timeout: float = 5.0
    sock: socket.socket | None = field(default=None, init=False, repr=False)
    fp: Any = field(default=None, init=False, repr=False)
    seq: int = field(default=0, init=False)

    def connect(self) -> dict[str, Any]:
        self.sock = socket.create_connection((self.host,self.port),timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.fp = self.sock.makefile("rwb", buffering=0)
        return self.request("hello", {"protocol":PROTOCOL_VERSION,"client":"ROMancer"})

    def close(self) -> None:
        try:
            if self.fp: self.fp.close()
        finally:
            if self.sock: self.sock.close()
        self.fp = None; self.sock = None

    def __enter__(self): self.connect(); return self
    def __exit__(self,*_): self.close()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.fp is None: raise DebugBridgeError("Debug bridge is not connected")
        self.seq += 1
        req={"id":self.seq,"method":method,"params":params or {}}
        self.fp.write((json.dumps(req,separators=(",",":"))+"\n").encode())
        raw=self.fp.readline()
        if not raw: raise DebugBridgeError("Debug bridge disconnected")
        try: resp=json.loads(raw)
        except Exception as e: raise DebugBridgeError(f"Invalid bridge response: {raw[:200]!r}") from e
        if resp.get("id") != self.seq: raise DebugBridgeError("Mismatched response id")
        if not resp.get("ok",False): raise DebugBridgeError(str(resp.get("error","debug bridge request failed")))
        return resp.get("result",{})

    def capabilities(self): return self.request("capabilities")
    def pause(self): return self.request("pause")
    def resume(self): return self.request("resume")
    def step(self,count:int=1): return self.request("step",{"count":count})
    def registers(self): return self.request("registers")
    def read_memory(self,address:int,size:int=1,domain:str="cpu"): return self.request("read_memory",{"address":address,"size":size,"domain":domain})
    def write_memory(self,address:int,data:list[int],domain:str="cpu"): return self.request("write_memory",{"address":address,"data":data,"domain":domain})
    def breakpoint(self,address:int): return self.request("breakpoint",{"address":address})
    def watchpoint(self,address:int,size:int=1,access:str="write"): return self.request("watchpoint",{"address":address,"size":size,"access":access})
    def run_until_stop(self,max_steps:int=100000): return self.request("run_until_stop",{"max_steps":max_steps})


class FixtureDebugBridge:
    """Small deterministic bridge server used by v11 self-test.

    This proves the transport and request contract without representing any
    third-party emulator as connected.
    """
    def __init__(self, host="127.0.0.1", port=0):
        self.host=host; self.port=port; self.thread=None; self.server=None
        self.memory={0x2000:0}; self.regs={"pc":0x1000,"a":5,"x":0,"y":0}; self.watch=None; self.running=False

    def _dispatch(self,m,p):
        if m=="hello": return {"protocol":PROTOCOL_VERSION,"backend":"fixture","live":True}
        if m=="capabilities": return {"capabilities":["pause","resume","step_instruction","read_registers","read_memory","write_memory","execute_breakpoint","write_watchpoint"]}
        if m=="pause": self.running=False; return {"paused":True}
        if m=="resume": self.running=True; return {"running":True}
        if m=="step":
            self.regs["pc"]+=2; return {"steps":int(p.get("count",1)),"registers":dict(self.regs)}
        if m=="registers": return dict(self.regs)
        if m=="read_memory":
            a=int(p["address"]); n=int(p.get("size",1)); return {"data":[self.memory.get(a+i,0) for i in range(n)]}
        if m=="write_memory":
            a=int(p["address"]); data=list(p.get("data",[]))
            for i,b in enumerate(data): self.memory[a+i]=int(b)&255
            return {"written":len(data)}
        if m=="breakpoint": return {"breakpoint":int(p["address"])}
        if m=="watchpoint": self.watch=(int(p["address"]),int(p.get("size",1)),p.get("access","write")); return {"watchpoint":self.watch}
        if m=="run_until_stop":
            self.memory[0x2000]=5; self.regs["pc"]=0x1002
            return {"reason":"watchpoint","address":0x2000,"pc":0x1002,"registers":dict(self.regs),"value":5}
        raise DebugBridgeError(f"unsupported fixture method {m}")

    def start(self):
        ready=threading.Event()
        def worker():
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind((self.host,self.port)); s.listen(1)
                self.server=s; self.port=s.getsockname()[1]; ready.set()
                conn,_=s.accept()
                with conn, conn.makefile("rwb",buffering=0) as fp:
                    while True:
                        line=fp.readline()
                        if not line: break
                        try:
                            req=json.loads(line); rid=req.get("id")
                            result=self._dispatch(req.get("method"),req.get("params") or {})
                            resp={"id":rid,"ok":True,"result":result}
                        except Exception as e:
                            resp={"id":req.get("id") if 'req' in locals() else None,"ok":False,"error":str(e)}
                        fp.write((json.dumps(resp,separators=(",",":"))+"\n").encode())
        self.thread=threading.Thread(target=worker,daemon=True); self.thread.start(); ready.wait(2)
        return self.port

    def stop(self):
        if self.thread: self.thread.join(timeout=.5)


def bridge_probe(host:str,port:int,timeout:float=3.0)->dict[str,Any]:
    c=DebugBridgeClient(host,port,timeout)
    try:
        hello=c.connect(); caps=c.capabilities(); regs=c.registers()
        return {"tool":"ROMancer","feature":"v11 live debug bridge probe","ok":True,"hello":hello,"capabilities":caps,"registers":regs}
    except Exception as e:
        return {"tool":"ROMancer","feature":"v11 live debug bridge probe","ok":False,"error":str(e)}
    finally:
        c.close()
