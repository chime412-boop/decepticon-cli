import tempfile, unittest, time
from session_automata import SessionAutomata
from session_automata.core import PROTECTED_CURRENT

class T(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.a=SessionAutomata(self.tmp.name)
        self.p1=self.a.upsert_profile("xc","chrome","xc",10)
        self.p2=self.a.upsert_profile("chime","chrome","chime",20)
        for p in (self.p1,self.p2): self.a.bind_capability("gemini",p)
    def tearDown(self): self.tmp.cleanup()

    def test_current_chat_is_protected(self):
        self.assertIsNotNone(self.a.is_protected(PROTECTED_CURRENT))
        self.assertIsNone(self.a.is_protected("https://chatgpt.com/c/other"))

    def test_candidate_priority(self):
        self.assertEqual(self.p1,self.a.candidates("gemini")[0]["id"])

    def test_failure_cooldown_rotates(self):
        self.a.record_attempt("gemini",self.p1,"probe",False,{"error":"dead"})
        self.assertEqual(self.p2,self.a.candidates("gemini")[0]["id"])

    def test_success_clears_failures(self):
        self.a.record_attempt("gemini",self.p1,"probe",False)
        c=self.a._conn(); c.execute("UPDATE provider_profiles SET cooldown_until=0 WHERE provider='gemini' AND profile_id=?",(self.p1,)); c.commit(); c.close()
        self.a.record_attempt("gemini",self.p1,"probe",True)
        row=[x for x in self.a.status()["providers"] if x["profile_id"]==self.p1][0]
        self.assertEqual("READY",row["last_status"]); self.assertEqual(0,row["fail_count"])

    def test_lease_excludes_duplicate_owner(self):
        l1=self.a.acquire("gemini",self.p1,"agentbus",60)
        self.assertTrue(l1)
        self.assertIsNone(self.a.acquire("gemini",self.p1,"other",60))
        self.a.release(l1)
        self.assertTrue(self.a.acquire("gemini",self.p1,"other",60))

if __name__=="__main__": unittest.main()
