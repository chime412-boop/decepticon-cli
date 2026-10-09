import asyncio, tempfile, unittest
from session_automata import SessionAutomata, ensure_provider_view
from session_automata.core import PROTECTED_CURRENT

class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.a=SessionAutomata(self.tmp.name)
        self.xc=self.a.upsert_profile("xc","chrome","xc",10)
        self.chime=self.a.upsert_profile("chime","chrome","chime",20)
        for p in (self.xc,self.chime): self.a.bind_capability("gemini",p)
    def tearDown(self): self.tmp.cleanup()

    def arun(self,coro): return asyncio.run(coro)

    def test_existing_ready_view_no_launch(self):
        calls=[]
        async def probe(p): return {"ok":True,"url":"https://gemini.google.com/app","engineReady":True,"renderReady":True}
        async def recover(*x): calls.append("recover"); return {"ok":False}
        async def launch(*x): calls.append("launch"); return {"ok":False}
        out=self.arun(ensure_provider_view(self.a,"gemini","bus",probe,recover,launch))
        self.assertTrue(out["ok"]); self.assertEqual("existing",out["source"]); self.assertEqual([],calls)

    def test_protected_view_forces_alternate_profile(self):
        state={"ready":False}; calls=[]
        async def probe(p):
            if state["ready"]: return {"ok":True,"url":"https://gemini.google.com/app","engineReady":True,"renderReady":True}
            return {"ok":True,"url":PROTECTED_CURRENT,"engineReady":True,"renderReady":True}
        async def recover(p,c):
            calls.append(("recover",c["alias"])); return {"ok":False}
        async def launch(p,c,url):
            calls.append(("launch",c["alias"],url)); state["ready"]=True; return {"ok":True}
        out=self.arun(ensure_provider_view(self.a,"gemini","bus",probe,recover,launch))
        self.assertTrue(out["ok"]); self.assertEqual("launch_recover",out["source"])
        self.assertEqual("xc",out["profile"]["alias"])
        self.assertTrue(out["lease_id"])

    def test_failed_candidate_rotates(self):
        state={"current":None}; calls=[]
        async def probe(p):
            if state["current"]=="chime": return {"ok":True,"url":"https://gemini.google.com/app","engineReady":True,"renderReady":True}
            return {"ok":False}
        async def recover(p,c): return {"ok":False}
        async def launch(p,c,url):
            calls.append(c["alias"])
            if c["alias"]=="xc": return {"ok":False,"error":"dead"}
            state["current"]="chime"; return {"ok":True}
        out=self.arun(ensure_provider_view(self.a,"gemini","bus",probe,recover,launch))
        self.assertTrue(out["ok"]); self.assertEqual(["xc","chime"],calls)
        self.assertEqual("chime",out["profile"]["alias"])

if __name__=="__main__": unittest.main()
