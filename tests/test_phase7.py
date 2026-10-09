import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from work_memory_core import WorkMemory

class Phase7(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.w=WorkMemory(self.root/"runtime")
    def tearDown(self): self.tmp.cleanup()

    def test_supervisor_crashes_stale_session_and_alerts(self):
        s=self.w.register_session("chatgpt","gpt","NVIDIA","lab","s1")
        t=self.w.create_task("work","unfinished","lab","NVIDIA",s["id"],"P0")["task"]["id"]
        self.w.add_event(t,"EDIT","CODE_CHANGED","changed")
        future=datetime.now(timezone.utc)+timedelta(seconds=5)
        out=self.w.supervisor_tick(active_seconds=1,crash_seconds=2,now=future)
        self.assertEqual("CRASHED",self.w.get_session(s["id"])["status"])
        self.assertEqual("ORPHANED",self.w.get_task(t)["task"]["derived_state"])
        self.assertEqual(t,out["orphaned"][0]["task_id"])
        alerts=self.w.list_alerts()
        self.assertEqual("ORPHANED_WORK",alerts[0]["kind"])

    def test_real_kill_takeover_and_verified_completion(self):
        s1=self.w.register_session("worker","child","NVIDIA","lab","child-1")
        task=self.w.create_task("crash-e2e","survive worker death","lab","NVIDIA",s1["id"],"P0")["task"]["id"]
        self.w.add_event(task,"START","CODE_CHANGED","work started")
        marker=self.root/"started.txt"
        code=("from pathlib import Path; import time; "
              f"Path(r'{marker}').write_text('started',encoding='utf-8'); time.sleep(60)")
        proc=subprocess.Popen([sys.executable,"-c",code])
        deadline=time.time()+5
        while time.time()<deadline and not marker.exists():
            time.sleep(0.05)
        self.assertTrue(marker.exists())
        proc.kill(); proc.wait(timeout=5)
        future=datetime.now(timezone.utc)+timedelta(seconds=3)
        self.w.supervisor_tick(active_seconds=0.5,crash_seconds=1,now=future)
        self.assertEqual("CRASHED",self.w.get_session(s1["id"])["status"])
        self.assertEqual("ORPHANED",self.w.get_task(task)["task"]["derived_state"])

        s2=self.w.register_session("worker","replacement","NVIDIA","lab","child-2")
        claim=self.w.claim_task(task,s2["id"])
        self.assertEqual("TAKEOVER",claim["action"])
        self.w.add_event(task,"RESUME","EXECUTED","replacement resumed")
        self.w.add_event(task,"READBACK","OBSERVED","state reconstructed")
        self.w.verify_e2e(task,"replacement completed end-to-end")
        self.assertEqual("COMPLETED",self.w.get_task(task)["task"]["derived_state"])

    def test_alert_acknowledgement(self):
        s=self.w.register_session("worker","x","NVIDIA","lab","x")
        t=self.w.create_task("x","x","lab","NVIDIA",s["id"],"P0")["task"]["id"]
        future=datetime.now(timezone.utc)+timedelta(seconds=3)
        self.w.supervisor_tick(active_seconds=0.5,crash_seconds=1,now=future)
        alert=self.w.list_alerts()[0]
        self.w.acknowledge_alert(alert["id"])
        self.assertEqual([],self.w.list_alerts())

if __name__=="__main__": unittest.main()
