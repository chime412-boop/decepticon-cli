import json, uuid
from .schema import EVIDENCE_LEVELS
from .storage import Storage, utc_now

class WorkMemory:
    def __init__(self,root):
        self.storage=Storage(root); self.storage.init()
    def _id(self,p): return f"{p}_{uuid.uuid4().hex}"
    def register_session(self,provider,model="",machine="",project="",external_session_id=""):
        now=utc_now(); con=self.storage.connect()
        row=con.execute("SELECT * FROM sessions WHERE provider=? AND machine=? AND project=? AND external_session_id=?",
            (provider,machine,project,external_session_id)).fetchone()
        if row:
            con.execute("UPDATE sessions SET status='ACTIVE',heartbeat_at=?,ended_at=NULL WHERE id=?",(now,row["id"]))
            con.commit(); out=dict(con.execute("SELECT * FROM sessions WHERE id=?",(row["id"],)).fetchone()); con.close(); return out
        sid=self._id("ses")
        con.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?, 'ACTIVE',?,?,NULL)",
            (sid,provider,model,machine,project,external_session_id,now,now))
        con.commit(); out=dict(con.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()); con.close(); return out
    def create_task(self,title,objective,project="",machine="",owner_session_id=None,priority="P2"):
        tid=self._id("task"); now=utc_now(); con=self.storage.connect()
        con.execute("""INSERT INTO tasks(id,title,objective,project,machine,owner_session_id,declared_state,derived_state,priority,created_at,updated_at)
        VALUES(?,?,?,?,?,?,'PLANNED','PLANNED',?,?,?)""",(tid,title,objective,project,machine,owner_session_id,priority,now,now))
        con.commit(); con.close(); self.storage.rebuild_search(); return self.get_task(tid)
    def get_task(self,tid):
        con=self.storage.connect(); t=con.execute("SELECT * FROM tasks WHERE id=?",(tid,)).fetchone()
        if not t: con.close(); raise KeyError(tid)
        ev=[dict(x) for x in con.execute("SELECT * FROM events WHERE task_id=? ORDER BY seq",(tid,))]
        con.close(); return {"task":dict(t),"events":ev}
    def set_declared_state(self,tid,state):
        con=self.storage.connect(); con.execute("UPDATE tasks SET declared_state=?,updated_at=? WHERE id=?",(state,utc_now(),tid)); con.commit(); con.close()
    def add_event(self,task_id,event_type,evidence_level,summary,session_id=None,details=None,idempotency_key=None):
        if evidence_level not in EVIDENCE_LEVELS: raise ValueError(evidence_level)
        eid=self._id("evt"); now=utc_now(); details=details or {}
        con=self.storage.connect()
        con.execute("""INSERT INTO events(event_id,task_id,session_id,event_type,evidence_level,summary,details_json,idempotency_key,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",(eid,task_id,session_id,event_type,evidence_level,summary,json.dumps(details,ensure_ascii=False,sort_keys=True),idempotency_key,now))
        self._derive(con,task_id); con.commit(); con.close()
        payload={"event_id":eid,"task_id":task_id,"session_id":session_id,"event_type":event_type,"evidence_level":evidence_level,"summary":summary,"details":details,"idempotency_key":idempotency_key,"created_at":now}
        self.storage.append_event(payload); self.storage.rebuild_search(); return payload
    def _derive(self,con,tid):
        levels={r["evidence_level"] for r in con.execute("SELECT evidence_level FROM events WHERE task_id=?",(tid,))}
        if "VERIFIED_E2E" in levels: state="COMPLETED"
        elif "RECONCILED" in levels or "OBSERVED" in levels: state="VERIFIED"
        elif "SIDE_EFFECT_OUTCOME" in levels or "EXECUTED" in levels: state="IMPLEMENTED"
        elif "SIDE_EFFECT_INTENT" in levels or "CODE_CHANGED" in levels: state="STARTED"
        else: state="PLANNED"
        con.execute("UPDATE tasks SET derived_state=?,updated_at=? WHERE id=?",(state,utc_now(),tid))
    def begin_side_effect(self,task_id,idempotency_key,summary,session_id=None,details=None):
        con=self.storage.connect(); old=con.execute("SELECT * FROM side_effects WHERE idempotency_key=?",(idempotency_key,)).fetchone(); con.close()
        if old: return {"duplicate":True,"side_effect":dict(old)}
        ev=self.add_event(task_id,"SIDE_EFFECT_INTENT","SIDE_EFFECT_INTENT",summary,session_id,details,idempotency_key)
        now=utc_now(); con=self.storage.connect()
        con.execute("INSERT INTO side_effects VALUES(?,?,?,NULL,NULL,'INTENT_RECORDED',?,?)",(idempotency_key,task_id,ev["event_id"],now,now))
        con.commit(); out=dict(con.execute("SELECT * FROM side_effects WHERE idempotency_key=?",(idempotency_key,)).fetchone()); con.close()
        return {"duplicate":False,"side_effect":out}
    def record_side_effect_outcome(self,task_id,idempotency_key,summary,session_id=None,details=None):
        con=self.storage.connect(); row=con.execute("SELECT * FROM side_effects WHERE idempotency_key=?",(idempotency_key,)).fetchone(); con.close()
        if not row: raise ValueError("side effect intent missing")
        if row["outcome_event_id"]: return {"duplicate":True,"side_effect":dict(row)}
        ev=self.add_event(task_id,"SIDE_EFFECT_OUTCOME","SIDE_EFFECT_OUTCOME",summary,session_id,details,idempotency_key)
        con=self.storage.connect(); con.execute("UPDATE side_effects SET outcome_event_id=?,status='OUTCOME_RECORDED',updated_at=? WHERE idempotency_key=?",(ev["event_id"],utc_now(),idempotency_key)); con.commit()
        out=dict(con.execute("SELECT * FROM side_effects WHERE idempotency_key=?",(idempotency_key,)).fetchone()); con.close(); return {"duplicate":False,"side_effect":out}
    def reconcile_side_effect(self,task_id,idempotency_key,summary):
        ev=self.add_event(task_id,"RECONCILED","RECONCILED",summary,idempotency_key=idempotency_key)
        con=self.storage.connect(); con.execute("UPDATE side_effects SET reconciliation_event_id=?,status='RECONCILED',updated_at=? WHERE idempotency_key=?",(ev["event_id"],utc_now(),idempotency_key)); con.commit(); con.close(); return ev
    def verify_e2e(self,task_id,summary): return self.add_event(task_id,"VERIFIED_E2E","VERIFIED_E2E",summary)
    def end_session(self,session_id,crashed=False):
        now=utc_now(); state="CRASHED" if crashed else "ENDED"; con=self.storage.connect()
        con.execute("UPDATE sessions SET status=?,ended_at=?,heartbeat_at=? WHERE id=?",(state,now,now,session_id))
        con.execute("UPDATE tasks SET derived_state='ORPHANED',updated_at=? WHERE owner_session_id=? AND derived_state!='COMPLETED'",(now,session_id))
        con.commit(); con.close()
    def unresolved_side_effects(self):
        con=self.storage.connect(); rows=[dict(x) for x in con.execute("SELECT * FROM side_effects WHERE status='INTENT_RECORDED'")]; con.close(); return rows
    def pending(self):
        con=self.storage.connect(); rows=[dict(x) for x in con.execute("SELECT * FROM tasks WHERE derived_state!='COMPLETED'")]; con.close(); return rows
    def search(self,q):
        con=self.storage.connect(); rows=[dict(x) for x in con.execute("SELECT entity_type,entity_id,title,body,project,machine FROM search_index WHERE search_index MATCH ?",(q,))]; con.close(); return rows
    def health(self):
        con=self.storage.connect(); out={t:con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("sessions","tasks","events","side_effects")}; con.close(); return {"ok":True,**out}
