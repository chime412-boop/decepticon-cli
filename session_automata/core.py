from __future__ import annotations
import json, sqlite3, time, uuid
from pathlib import Path
from urllib.parse import urlparse

PROVIDER_URLS = {
    "chatgpt":"https://chatgpt.com/",
    "gemini":"https://gemini.google.com/app",
    "claude":"https://claude.ai/new",
    "perplexity":"https://www.perplexity.ai/",
    "qwen":"https://chat.qwen.ai/",
    "deepseek":"https://chat.deepseek.com/",
}
PROTECTED_CURRENT = "https://chatgpt.com/c/6ac85796-6184-83e9-b7f6-e47a664554df"

class SessionAutomata:
    def __init__(self, root: str|Path):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/"session_automata.sqlite3"
        self._init()

    def _conn(self):
        c=sqlite3.connect(self.db,timeout=15); c.row_factory=sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=15000")
        return c

    def _init(self):
        c=self._conn()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS profiles(
          id TEXT PRIMARY KEY, alias TEXT NOT NULL, browser TEXT NOT NULL,
          profile_dir TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 100,
          enabled INTEGER NOT NULL DEFAULT 1, metadata_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(browser,profile_dir)
        );
        CREATE TABLE IF NOT EXISTS provider_profiles(
          provider TEXT NOT NULL, profile_id TEXT NOT NULL,
          capability TEXT NOT NULL DEFAULT 'UNKNOWN',
          last_status TEXT NOT NULL DEFAULT 'UNKNOWN',
          last_ok_at REAL, last_fail_at REAL, fail_count INTEGER NOT NULL DEFAULT 0,
          cooldown_until REAL NOT NULL DEFAULT 0,
          PRIMARY KEY(provider,profile_id),
          FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS leases(
          lease_id TEXT PRIMARY KEY, provider TEXT NOT NULL, profile_id TEXT NOT NULL,
          owner TEXT NOT NULL, status TEXT NOT NULL, acquired_at REAL NOT NULL,
          expires_at REAL NOT NULL, released_at REAL,
          FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS protected_targets(
          canonical_url TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attempts(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, profile_id TEXT,
          step TEXT NOT NULL, ok INTEGER NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}',
          created_at REAL NOT NULL
        );
        """)
        c.execute("INSERT OR IGNORE INTO protected_targets VALUES(?,?,?)",
                  (self.canonical_url(PROTECTED_CURRENT),"CURRENT_USER_SESSION_DO_NOT_TOUCH",time.time()))
        c.commit(); c.close()

    @staticmethod
    def canonical_url(url:str)->str:
        p=urlparse(str(url or "").strip())
        if not p.scheme or not p.netloc: return str(url or "").strip()
        return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"

    def protect(self,url,reason):
        c=self._conn(); c.execute("INSERT OR REPLACE INTO protected_targets VALUES(?,?,?)",
                                  (self.canonical_url(url),str(reason),time.time())); c.commit(); c.close()

    def is_protected(self,url):
        u=self.canonical_url(url); c=self._conn()
        row=c.execute("SELECT reason FROM protected_targets WHERE canonical_url=?",(u,)).fetchone()
        c.close(); return dict(row) if row else None

    def upsert_profile(self,alias,browser,profile_dir,priority=100,metadata=None):
        c=self._conn()
        old=c.execute("SELECT * FROM profiles WHERE browser=? AND profile_dir=?",(browser,profile_dir)).fetchone()
        if old:
            c.execute("UPDATE profiles SET alias=?,priority=?,metadata_json=? WHERE id=?",
                      (alias,int(priority),json.dumps(metadata or {},ensure_ascii=False),old["id"]))
            pid=old["id"]
        else:
            pid="prof_"+uuid.uuid4().hex
            c.execute("""INSERT INTO profiles
                      (id,alias,browser,profile_dir,priority,enabled,metadata_json)
                      VALUES(?,?,?,?,?,1,?)""",
                      (pid,alias,browser,profile_dir,int(priority),json.dumps(metadata or {},ensure_ascii=False)))
        c.commit(); c.close(); return pid

    def bind_capability(self,provider,profile_id,capability="KNOWN"):
        c=self._conn()
        c.execute("""INSERT INTO provider_profiles(provider,profile_id,capability)
                     VALUES(?,?,?) ON CONFLICT(provider,profile_id)
                     DO UPDATE SET capability=excluded.capability""",(provider,profile_id,capability))
        c.commit(); c.close()

    def candidates(self,provider,now=None):
        now=float(now or time.time()); c=self._conn()
        rows=c.execute("""SELECT p.*,pp.capability,pp.last_status,pp.fail_count,pp.cooldown_until
          FROM profiles p JOIN provider_profiles pp ON pp.profile_id=p.id
          WHERE pp.provider=? AND p.enabled=1 AND pp.cooldown_until<=?
          ORDER BY CASE pp.last_status WHEN 'READY' THEN 0 WHEN 'RECOVERED' THEN 1 ELSE 2 END,
                   p.priority ASC, pp.fail_count ASC, p.alias ASC""",(provider,now)).fetchall()
        c.close(); return [dict(r) for r in rows]

    def record_attempt(self,provider,profile_id,step,ok,detail=None):
        now=time.time(); c=self._conn()
        c.execute("INSERT INTO attempts(provider,profile_id,step,ok,detail_json,created_at) VALUES(?,?,?,?,?,?)",
                  (provider,profile_id,step,1 if ok else 0,json.dumps(detail or {},ensure_ascii=False),now))
        if profile_id:
            if ok:
                c.execute("""UPDATE provider_profiles SET last_status=?,last_ok_at=?,fail_count=0,cooldown_until=0
                             WHERE provider=? AND profile_id=?""",
                          ("READY" if step=="probe" else "RECOVERED",now,provider,profile_id))
            else:
                row=c.execute("SELECT fail_count FROM provider_profiles WHERE provider=? AND profile_id=?",
                              (provider,profile_id)).fetchone()
                fails=int(row["fail_count"] if row else 0)+1
                cooldown=min(900,30*(2**min(fails-1,5)))
                c.execute("""UPDATE provider_profiles SET last_status='FAILED',last_fail_at=?,fail_count=?,cooldown_until=?
                             WHERE provider=? AND profile_id=?""",(now,fails,now+cooldown,provider,profile_id))
        c.commit(); c.close()

    def acquire(self,provider,profile_id,owner,ttl=120):
        now=time.time(); c=self._conn()
        active=c.execute("""SELECT lease_id FROM leases WHERE provider=? AND profile_id=? AND status='ACTIVE' AND expires_at>?""",
                         (provider,profile_id,now)).fetchone()
        if active: c.close(); return None
        lid="lease_"+uuid.uuid4().hex
        try:
            c.execute("""INSERT INTO leases
                      (lease_id,provider,profile_id,owner,status,acquired_at,expires_at,released_at)
                      VALUES(?,?,?,?,?,?,?,NULL)""",
                      (lid,provider,profile_id,owner,"ACTIVE",now,now+ttl))
            c.commit()
            return lid
        finally:
            c.close()

    def release(self,lease_id):
        c=self._conn(); c.execute("UPDATE leases SET status='RELEASED',released_at=? WHERE lease_id=?",
                                  (time.time(),lease_id)); c.commit(); c.close()

    def profile(self,profile_id):
        c=self._conn(); row=c.execute("SELECT * FROM profiles WHERE id=?",(profile_id,)).fetchone(); c.close()
        return dict(row) if row else None

    def status(self):
        c=self._conn()
        out={
          "profiles":[dict(x) for x in c.execute("SELECT * FROM profiles ORDER BY priority,alias")],
          "providers":[dict(x) for x in c.execute("SELECT * FROM provider_profiles ORDER BY provider,profile_id")],
          "active_leases":[dict(x) for x in c.execute("SELECT * FROM leases WHERE status='ACTIVE' AND expires_at>?",(time.time(),))],
          "protected":[dict(x) for x in c.execute("SELECT * FROM protected_targets")],
        }
        c.close(); return out
