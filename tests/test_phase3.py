import tempfile
import unittest
from work_memory_core import WorkMemory

class Phase3(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.w=WorkMemory(self.tmp.name)
        self.s1=self.w.register_session("chatgpt","gpt","NVIDIA","PAY","s1")
        self.s2=self.w.register_session("claude","claude","NVIDIA","PAY","s2")
        self.t=self.w.create_task("gateway","repair oauth","PAY","NVIDIA",self.s1["id"],"P0")["task"]["id"]
    def tearDown(self): self.tmp.cleanup()

    def test_structured_handoff_roundtrip(self):
        h=self.w.create_handoff(
            self.t,self.s1["id"],"repair oauth","PARTIAL",
            next_action="verify public MCP",blocked_on="401",
            ruled_out=[{"path":"restart","reason":"service healthy"}],
            files=["gateway_dcr.py"],commands=["health"],results=["8773 OK"],
            errors=["public 401"],evidence=["OBSERVED: local OK"],to_session_id=self.s2["id"])
        self.assertEqual("verify public MCP",h["next_action"])
        self.assertEqual("restart",h["ruled_out"][0]["path"])
        self.assertEqual(["gateway_dcr.py"],h["files"])

    def test_latest_handoff_scoped(self):
        self.w.create_handoff(self.t,self.s1["id"],"repair oauth","PARTIAL",next_action="readback")
        h=self.w.latest_handoff("PAY","NVIDIA")
        self.assertEqual(self.t,h["task_id"])

    def test_handoff_updates_task_next_and_blocker(self):
        self.w.create_handoff(self.t,self.s1["id"],"repair oauth","BLOCKED",next_action="inspect DCR",blocked_on="401")
        task=self.w.get_task(self.t)["task"]
        self.assertEqual("inspect DCR",task["next_action"])
        self.assertEqual("401",task["blocked_on"])

    def test_context_bundle_is_bounded_and_useful(self):
        for i in range(20):
            self.w.add_event(self.t,"NOTE","PROPOSED",f"event {i}")
        self.w.create_handoff(self.t,self.s1["id"],"repair oauth","PARTIAL",next_action="continue")
        bundle=self.w.context_bundle("PAY","NVIDIA",limit_events=5)
        self.assertEqual(5,len(bundle["recent_events"]))
        self.assertEqual("continue",bundle["latest_handoff"]["next_action"])
        self.assertTrue(bundle["pending"])
        self.assertTrue(bundle["sessions"])

if __name__=="__main__": unittest.main()
