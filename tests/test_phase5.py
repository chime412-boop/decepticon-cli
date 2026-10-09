import tempfile
import unittest
from pathlib import Path
from work_memory_core import WorkMemory

class Phase5(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.w=WorkMemory(self.root/"runtime")
        self.skill=self.root/"skill"; self.skill.mkdir()
        (self.skill/"SKILL.md").write_text("# Durable Execution\nDo read-back before retry.\n",encoding="utf-8")
    def tearDown(self): self.tmp.cleanup()

    def test_unverified_skill_cannot_activate(self):
        s=self.w.register_skill(self.skill,"durable-execution","1.0.0","book-to-skill",False)
        with self.assertRaises(RuntimeError):
            self.w.activate_skill(s["id"],"PAY","NVIDIA")

    def test_verified_skill_activates(self):
        s=self.w.register_skill(self.skill,"durable-execution","1.0.0","book-to-skill",True)
        self.w.activate_skill(s["id"],"PAY","NVIDIA")
        active=self.w.active_skills("PAY","NVIDIA")
        self.assertEqual("durable-execution",active[0]["name"])

    def test_mutated_same_version_is_rejected(self):
        self.w.register_skill(self.skill,"durable-execution","1.0.0","book-to-skill",False)
        (self.skill/"SKILL.md").write_text("# changed",encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.w.register_skill(self.skill,"durable-execution","1.0.0","book-to-skill",False)

    def test_verification_detects_post_registration_change(self):
        s=self.w.register_skill(self.skill,"durable-execution","1.0.0","book-to-skill",False)
        (self.skill/"SKILL.md").write_text("# tampered",encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.w.verify_skill(s["id"])

if __name__=="__main__": unittest.main()
