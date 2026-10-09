import json, sqlite3
from pathlib import Path
from datetime import datetime, timezone

def utc_now(): return datetime.now(timezone.utc).isoformat()

class Storage:
    def __init__(self, root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.db_path=self.root/"work_memory.db"; self.events_path=self.root/"events.jsonl"
    def connect(self):
        con=sqlite3.connect(self.db_path); con.row_factory=sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA foreign_keys=ON"); return con
    def init(self):
        con=self.connect()
        con.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(
          id TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT DEFAULT '', machine TEXT DEFAULT '',
          project TEXT DEFAULT '', external_session_id TEXT DEFAULT '', status TEXT NOT NULL,
          started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, ended_at TEXT,
          UNIQUE(provider,machine,project,external_session_id));
        CREATE TABLE IF NOT EXISTS tasks(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, objective TEXT NOT NULL, project TEXT DEFAULT '',
          machine TEXT DEFAULT '', owner_session_id TEXT, declared_state TEXT NOT NULL,
          derived_state TEXT NOT NULL, priority TEXT DEFAULT 'P2', next_action TEXT DEFAULT '',
          blocked_on TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          FOREIGN KEY(owner_session_id) REFERENCES sessions(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, task_id TEXT,
          session_id TEXT, event_type TEXT NOT NULL, evidence_level TEXT NOT NULL, summary TEXT NOT NULL,
          details_json TEXT DEFAULT '{}', idempotency_key TEXT, created_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
          FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_event_idem ON events(idempotency_key,event_type)
          WHERE idempotency_key IS NOT NULL;
        CREATE TABLE IF NOT EXISTS side_effects(
          idempotency_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, intent_event_id TEXT NOT NULL,
          outcome_event_id TEXT, reconciliation_event_id TEXT, status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS task_claims(
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          task_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          action TEXT NOT NULL,
          previous_session_id TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
          FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS handoffs(
          id TEXT PRIMARY KEY,
          task_id TEXT,
          from_session_id TEXT,
          to_session_id TEXT,
          project TEXT NOT NULL DEFAULT '',
          machine TEXT NOT NULL DEFAULT '',
          objective TEXT NOT NULL,
          status TEXT NOT NULL,
          next_action TEXT NOT NULL DEFAULT '',
          blocked_on TEXT NOT NULL DEFAULT '',
          ruled_out_json TEXT NOT NULL DEFAULT '[]',
          files_json TEXT NOT NULL DEFAULT '[]',
          commands_json TEXT NOT NULL DEFAULT '[]',
          results_json TEXT NOT NULL DEFAULT '[]',
          errors_json TEXT NOT NULL DEFAULT '[]',
          evidence_json TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE SET NULL,
          FOREIGN KEY(from_session_id) REFERENCES sessions(id) ON DELETE SET NULL,
          FOREIGN KEY(to_session_id) REFERENCES sessions(id) ON DELETE SET NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
          entity_type, entity_id UNINDEXED, title, body, project, machine);
        """)
        con.commit(); con.close(); self.events_path.touch(exist_ok=True)
    def append_event(self,payload):
        with self.events_path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(payload,ensure_ascii=False,sort_keys=True)+"\n")
    def rebuild_search(self):
        con=self.connect(); con.execute("DELETE FROM search_index")
        for r in con.execute("SELECT * FROM tasks"):
            con.execute("INSERT INTO search_index VALUES(?,?,?,?,?,?)",
                ("task",r["id"],r["title"]," ".join(filter(None,[r["objective"],r["next_action"],r["blocked_on"]])),r["project"],r["machine"]))
        for r in con.execute("SELECT e.*,t.title,t.project,t.machine FROM events e LEFT JOIN tasks t ON t.id=e.task_id"):
            con.execute("INSERT INTO search_index VALUES(?,?,?,?,?,?)",
                ("event",r["event_id"],r["title"] or r["event_type"],r["summary"]+" "+r["details_json"],r["project"] or "",r["machine"] or ""))
        con.commit(); con.close()
