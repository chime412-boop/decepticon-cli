import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from work_memory_core import WorkMemory

class Phase2(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.w=WorkMemory(self.tmp.name)
        self.s1=self.w.register_session("chatgpt","gpt","NVIDIA","lab","s1")
        self.s2=self.w.register_session("claude","claude","NVIDIA","lab","s2")
        self.t=self.w.create_task("handoff","continue safely","lab","NVIDIA",self.s1["id"],"P0")["task"]["id"]
    def tearDown(self): self.tmp.cleanup()

    def test_heartbeat_keeps_active(self):
        self.w.heartbeat(self.s1["id"])
        self.assertEqual("ACTIVE",self.w.get_session(self.s1["id"])["status"])

    def test_stale_session_becomes_idle(self):
        old=datetime.now(timezone.utc)-timedelta(minutes=30)
        con=self.w.storage.connect()
        con.execute("UPDATE sessions SET heartbeat_at=? WHERE id=?",(old.isoformat(),self.s1["id"]))
        con.commit(); con.close()
        self.w.refresh_session_states(active_seconds=900)
        self.assertEqual("IDLE",self.w.get_session(self.s1["id"])["status"])

    def test_active_owner_blocks_takeover(self):
        with self.assertRaises(RuntimeError):
            self.w.claim_task(self.t,self.s2["id"])

    def test_terminal_owner_can_be_taken_over(self):
        self.w.end_session(self.s1["id"])
        result=self.w.claim_task(self.t,self.s2["id"])
        self.assertEqual("TAKEOVER",result["action"])
        self.assertEqual(self.s2["id"],self.w.get_task(self.t)["task"]["owner_session_id"])

    def test_claim_history_is_durable(self):
        self.w.end_session(self.s1["id"])
        self.w.claim_task(self.t,self.s2["id"])
        claims=self.w.list_claims(self.t)
        self.assertEqual(1,len(claims))
        self.assertEqual(self.s1["id"],claims[0]["previous_session_id"])

    def test_catch_up_audit_orphans_terminal_owner(self):
        self.w.end_session(self.s1["id"],crashed=True)
        con=self.w.storage.connect()
        con.execute("UPDATE tasks SET derived_state='STARTED' WHERE id=?",(self.t,))
        con.commit(); con.close()
        repaired=self.w.catch_up_audit()
        self.assertEqual(1,len(repaired))
        self.assertEqual("ORPHANED",self.w.get_task(self.t)["task"]["derived_state"])

if __name__=="__main__": unittest.main()
