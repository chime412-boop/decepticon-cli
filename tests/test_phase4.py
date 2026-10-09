import tempfile
import unittest
from work_memory_core import WorkMemory

class Phase4(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.w=WorkMemory(self.tmp.name)
        self.s=self.w.register_session("chatgpt","gpt","NVIDIA","lab","s1")
        self.t=self.w.create_task("send","external effect","lab","NVIDIA",self.s["id"],"P0")["task"]["id"]
    def tearDown(self): self.tmp.cleanup()

    def test_intent_requires_readback(self):
        self.w.begin_side_effect(self.t,"mail:42","send mail")
        plan=self.w.recovery_plan()
        self.assertEqual("READBACK_REQUIRED",plan[0]["next_action"])

    def test_positive_readback_reconciles_without_retry(self):
        self.w.begin_side_effect(self.t,"mail:42","send mail")
        result=self.w.reconcile_from_readback(self.t,"mail:42",True,{"message_id":"abc"})
        self.assertEqual("EFFECT_CONFIRMED",result["decision"])
        self.assertEqual([],self.w.unresolved_side_effects())
        checks=self.w.list_recovery_checks("mail:42")
        self.assertEqual("EFFECT_CONFIRMED",checks[-1]["decision"])

    def test_negative_readback_allows_retry(self):
        self.w.begin_side_effect(self.t,"download:1","download")
        result=self.w.reconcile_from_readback(self.t,"download:1",False,{"file_exists":False})
        self.assertEqual("SAFE_TO_RETRY",result["decision"])
        plan=self.w.recovery_plan()
        self.assertEqual("RETRY_ALLOWED",plan[0]["next_action"])
        auth=self.w.authorize_retry(self.t,"download:1")
        self.assertTrue(auth["authorized"])

    def test_retry_blocked_without_negative_readback(self):
        self.w.begin_side_effect(self.t,"write:1","write")
        with self.assertRaises(RuntimeError):
            self.w.authorize_retry(self.t,"write:1")

    def test_unknown_readback_stays_unresolved(self):
        self.w.begin_side_effect(self.t,"remote:1","remote")
        result=self.w.reconcile_from_readback(self.t,"remote:1",None,{"reason":"service unreachable"})
        self.assertEqual("UNKNOWN",result["decision"])
        self.assertEqual("READBACK_REQUIRED",self.w.recovery_plan()[0]["next_action"])

if __name__=="__main__": unittest.main()
