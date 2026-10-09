import json,tempfile,unittest
from pathlib import Path
from work_memory_core import WorkMemory
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.w=WorkMemory(self.tmp.name)
  self.s=self.w.register_session("chatgpt","gpt-test","DESKTOP-UNJMQ99","lab","abc")
  self.t=self.w.create_task("Durable","Evidence-derived","lab","DESKTOP-UNJMQ99",self.s["id"],"P0")["task"]["id"]
 def tearDown(self): self.tmp.cleanup()
 def test_session_idempotent(self):
  s2=self.w.register_session("chatgpt","other","DESKTOP-UNJMQ99","lab","abc");self.assertEqual(self.s["id"],s2["id"])
 def test_declared_completed_not_real(self):
  self.w.set_declared_state(self.t,"COMPLETED");x=self.w.get_task(self.t)["task"];self.assertEqual("COMPLETED",x["declared_state"]);self.assertEqual("PLANNED",x["derived_state"])
 def test_completion_requires_e2e(self):
  self.w.add_event(self.t,"RUN","EXECUTED","ok");self.assertEqual("IMPLEMENTED",self.w.get_task(self.t)["task"]["derived_state"])
  self.w.add_event(self.t,"READBACK","OBSERVED","seen");self.assertEqual("VERIFIED",self.w.get_task(self.t)["task"]["derived_state"])
  self.w.verify_e2e(self.t,"e2e");self.assertEqual("COMPLETED",self.w.get_task(self.t)["task"]["derived_state"])
 def test_idempotent_side_effect(self):
  a=self.w.begin_side_effect(self.t,"send:42","send");b=self.w.begin_side_effect(self.t,"send:42","send");self.assertFalse(a["duplicate"]);self.assertTrue(b["duplicate"]);self.assertEqual(1,len(self.w.unresolved_side_effects()))
 def test_outcome_resolves_intent(self):
  self.w.begin_side_effect(self.t,"write:1","write");self.w.record_side_effect_outcome(self.t,"write:1","done");self.assertEqual([],self.w.unresolved_side_effects())
 def test_crash_orphans(self):
  self.w.add_event(self.t,"EDIT","CODE_CHANGED","changed");self.w.end_session(self.s["id"],True);self.assertEqual("ORPHANED",self.w.get_task(self.t)["task"]["derived_state"])
 def test_jsonl(self):
  e=self.w.add_event(self.t,"NOTE","PROPOSED","x");p=Path(self.tmp.name)/"events.jsonl";self.assertEqual(e["event_id"],json.loads(p.read_text(encoding="utf-8").splitlines()[-1])["event_id"])
 def test_search(self):
  self.w.add_event(self.t,"OBS","OBSERVED","gateway oauth");self.assertTrue(self.w.search("oauth"))
if __name__=="__main__": unittest.main()
