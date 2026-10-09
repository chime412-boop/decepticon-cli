import json
import sys
import tempfile
import unittest
from pathlib import Path
from work_memory_core import WorkMemory

class Phase6(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.w=WorkMemory(self.root/"runtime")
        self.s=self.w.register_session("system","runner","NVIDIA","lab","proc")
    def tearDown(self): self.tmp.cleanup()

    def test_process_defaults_disabled(self):
        p=self.w.register_process("demo",self.root,[sys.executable,"-c","print('x')"])
        self.assertEqual(0,p["enabled"])

    def test_dry_run_does_not_execute(self):
        marker=self.root/"marker.txt"
        p=self.w.register_process("demo",self.root,[sys.executable,"-c",f"open(r'{marker}','w').write('x')"])
        out=self.w.execute_process(p["id"],self.s["id"],dry_run=True)
        self.assertTrue(out["dry_run"]); self.assertFalse(marker.exists())

    def test_enabled_process_records_and_verifies(self):
        marker=self.root/"marker.txt"
        code=f"from pathlib import Path; Path(r'{marker}').write_text('ok',encoding='utf-8')"
        p=self.w.register_process("demo",self.root,[sys.executable,"-c",code],readback=[{"kind":"path_nonempty","path":str(marker)}],enabled=True)
        out=self.w.execute_process(p["id"],self.s["id"])
        self.assertEqual(0,out["returncode"])
        self.assertEqual("COMPLETED",out["derived_state"])
        self.assertTrue(marker.exists())

    def test_catalog_import(self):
        cat=self.root/"catalog.json"
        cat.write_text(json.dumps({"processes":[{"name":"x","cwd":str(self.root),"argv":[sys.executable,"-c","print(1)"]}]}),encoding="utf-8")
        imported=self.w.import_process_catalog(cat)
        self.assertEqual("x",imported[0]["name"])

if __name__=="__main__": unittest.main()
