import json, uuid
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone
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

    def recovery_plan(self):
        con=self.storage.connect()
        rows=[dict(x) for x in con.execute(
            "SELECT * FROM side_effects WHERE status IN ('INTENT_RECORDED','SAFE_TO_RETRY','RETRY_AUTHORIZED') ORDER BY created_at"
        )]
        con.close()
        plan=[]
        for row in rows:
            action="READBACK_REQUIRED" if row["status"]=="INTENT_RECORDED" else "RETRY_ALLOWED"
            plan.append({**row,"next_action":action})
        return plan

    def reconcile_from_readback(self,task_id,idempotency_key,observed,details=None):
        con=self.storage.connect()
        side=con.execute("SELECT * FROM side_effects WHERE idempotency_key=?",(idempotency_key,)).fetchone()
        if not side:
            con.close(); raise KeyError(idempotency_key)
        now=utc_now(); details=details or {}
        if observed is True:
            decision="EFFECT_CONFIRMED"
        elif observed is False:
            decision="SAFE_TO_RETRY"
        else:
            decision="UNKNOWN"
        con.execute("INSERT INTO recovery_checks(idempotency_key,observed,decision,details_json,created_at) VALUES(?,?,?,?,?)",
                    (idempotency_key,None if observed is None else int(observed),decision,json.dumps(details,ensure_ascii=False),now))
        if decision=="SAFE_TO_RETRY":
            con.execute("UPDATE side_effects SET status='SAFE_TO_RETRY',updated_at=? WHERE idempotency_key=?",(now,idempotency_key))
            con.commit(); con.close()
            return {"decision":decision,"idempotency_key":idempotency_key}
        if decision=="UNKNOWN":
            con.commit(); con.close()
            return {"decision":decision,"idempotency_key":idempotency_key}
        con.commit(); con.close()

        if not side["outcome_event_id"]:
            self.record_side_effect_outcome(task_id,idempotency_key,"effect confirmed by read-back",details=details)
        self.reconcile_side_effect(task_id,idempotency_key,"read-back reconciled external effect")
        return {"decision":decision,"idempotency_key":idempotency_key}

    def authorize_retry(self,task_id,idempotency_key,summary="retry authorized after negative read-back"):
        con=self.storage.connect()
        side=con.execute("SELECT * FROM side_effects WHERE idempotency_key=?",(idempotency_key,)).fetchone()
        con.close()
        if not side: raise KeyError(idempotency_key)
        if side["status"]!="SAFE_TO_RETRY":
            raise RuntimeError("retry not safe")
        event=self.add_event(task_id,"SIDE_EFFECT_RETRY_INTENT","SIDE_EFFECT_INTENT",summary,idempotency_key=None)
        con=self.storage.connect()
        con.execute("UPDATE side_effects SET status='RETRY_AUTHORIZED',updated_at=? WHERE idempotency_key=?",(utc_now(),idempotency_key))
        con.commit(); con.close()
        return {"authorized":True,"event_id":event["event_id"],"idempotency_key":idempotency_key}

    def list_recovery_checks(self,idempotency_key):
        con=self.storage.connect()
        rows=[dict(x) for x in con.execute("SELECT * FROM recovery_checks WHERE idempotency_key=? ORDER BY seq",(idempotency_key,))]
        con.close()
        for row in rows:
            row["details"]=json.loads(row.pop("details_json"))
        return rows

    def end_session(self,session_id,crashed=False):
        now=utc_now(); state="CRASHED" if crashed else "ENDED"; con=self.storage.connect()
        con.execute("UPDATE sessions SET status=?,ended_at=?,heartbeat_at=? WHERE id=?",(state,now,now,session_id))
        con.execute("UPDATE tasks SET derived_state='ORPHANED',updated_at=? WHERE owner_session_id=? AND derived_state!='COMPLETED'",(now,session_id))
        con.commit(); con.close()

    def heartbeat(self,session_id):
        now=utc_now(); con=self.storage.connect()
        cur=con.execute("UPDATE sessions SET heartbeat_at=?,status='ACTIVE' WHERE id=? AND ended_at IS NULL",(now,session_id))
        if cur.rowcount != 1:
            con.close(); raise KeyError(session_id)
        con.commit(); con.close()
        return self.get_session(session_id)

    def get_session(self,session_id):
        con=self.storage.connect()
        row=con.execute("SELECT * FROM sessions WHERE id=?",(session_id,)).fetchone()
        con.close()
        if not row: raise KeyError(session_id)
        return dict(row)

    def refresh_session_states(self,active_seconds=900,now=None):
        current=now or datetime.now(timezone.utc)
        con=self.storage.connect(); changed=[]
        for row in con.execute("SELECT * FROM sessions WHERE ended_at IS NULL"):
            beat=datetime.fromisoformat(row["heartbeat_at"])
            age=(current-beat).total_seconds()
            state="ACTIVE" if age <= active_seconds else "IDLE"
            if row["status"] != state:
                con.execute("UPDATE sessions SET status=? WHERE id=?",(state,row["id"]))
                changed.append({"session_id":row["id"],"from":row["status"],"to":state})
        con.commit(); con.close()
        return changed

    def claim_task(self,task_id,session_id,force=False):
        self.refresh_session_states()
        con=self.storage.connect()
        task=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
        session=con.execute("SELECT * FROM sessions WHERE id=?",(session_id,)).fetchone()
        if not task or not session:
            con.close(); raise KeyError(task_id if not task else session_id)
        prev=task["owner_session_id"]
        if prev and prev != session_id:
            owner=con.execute("SELECT * FROM sessions WHERE id=?",(prev,)).fetchone()
            if owner and owner["status"]=="ACTIVE" and not force:
                con.close(); raise RuntimeError("task owned by active session")
        action="CLAIM" if not prev else ("RECLAIM" if prev==session_id else "TAKEOVER")
        now=utc_now()
        con.execute("UPDATE tasks SET owner_session_id=?,updated_at=? WHERE id=?",(session_id,now,task_id))
        con.execute("INSERT INTO task_claims(task_id,session_id,action,previous_session_id,created_at) VALUES(?,?,?,?,?)",
                    (task_id,session_id,action,prev,now))
        con.commit(); con.close()
        return {"task_id":task_id,"session_id":session_id,"previous_session_id":prev,"action":action}

    def catch_up_audit(self):
        self.refresh_session_states()
        con=self.storage.connect(); repaired=[]
        sql=("SELECT t.id task_id,t.owner_session_id,s.status session_status,t.derived_state "
             "FROM tasks t LEFT JOIN sessions s ON s.id=t.owner_session_id "
             "WHERE t.owner_session_id IS NOT NULL AND t.derived_state!='COMPLETED'")
        rows=con.execute(sql).fetchall()
        now=utc_now()
        for row in rows:
            if row["session_status"] in ("ENDED","CRASHED","ORPHANED") and row["derived_state"]!="ORPHANED":
                con.execute("UPDATE tasks SET derived_state='ORPHANED',updated_at=? WHERE id=?",(now,row["task_id"]))
                repaired.append({"task_id":row["task_id"],"owner_session_id":row["owner_session_id"],"owner_status":row["session_status"]})
        con.commit(); con.close()
        return repaired

    def list_claims(self,task_id):
        con=self.storage.connect()
        rows=[dict(x) for x in con.execute("SELECT * FROM task_claims WHERE task_id=? ORDER BY seq",(task_id,))]
        con.close(); return rows

    def create_handoff(self,task_id,from_session_id,objective,status,next_action="",blocked_on="",
                       ruled_out=None,files=None,commands=None,results=None,errors=None,evidence=None,
                       to_session_id=None):
        task=self.get_task(task_id)["task"]
        hid=self._id("handoff"); now=utc_now()
        payload={
            "ruled_out": ruled_out or [],
            "files": files or [],
            "commands": commands or [],
            "results": results or [],
            "errors": errors or [],
            "evidence": evidence or [],
        }
        con=self.storage.connect()
        con.execute("""INSERT INTO handoffs(
            id,task_id,from_session_id,to_session_id,project,machine,objective,status,next_action,blocked_on,
            ruled_out_json,files_json,commands_json,results_json,errors_json,evidence_json,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (hid,task_id,from_session_id,to_session_id,task["project"],task["machine"],objective,status,next_action,blocked_on,
         json.dumps(payload["ruled_out"],ensure_ascii=False),json.dumps(payload["files"],ensure_ascii=False),
         json.dumps(payload["commands"],ensure_ascii=False),json.dumps(payload["results"],ensure_ascii=False),
         json.dumps(payload["errors"],ensure_ascii=False),json.dumps(payload["evidence"],ensure_ascii=False),now))
        con.execute("UPDATE tasks SET next_action=?,blocked_on=?,updated_at=? WHERE id=?",(next_action,blocked_on,now,task_id))
        con.commit(); con.close()
        return self.get_handoff(hid)

    def get_handoff(self,handoff_id):
        con=self.storage.connect(); row=con.execute("SELECT * FROM handoffs WHERE id=?",(handoff_id,)).fetchone(); con.close()
        if not row: raise KeyError(handoff_id)
        out=dict(row)
        for key in ("ruled_out","files","commands","results","errors","evidence"):
            out[key]=json.loads(out.pop(key+"_json"))
        return out

    def latest_handoff(self,project="",machine=""):
        con=self.storage.connect()
        clauses=[]; params=[]
        if project: clauses.append("project=?"); params.append(project)
        if machine: clauses.append("machine=?"); params.append(machine)
        sql="SELECT id FROM handoffs"
        if clauses: sql+=" WHERE "+" AND ".join(clauses)
        sql+=" ORDER BY created_at DESC LIMIT 1"
        row=con.execute(sql,params).fetchone(); con.close()
        return self.get_handoff(row["id"]) if row else None

    def context_bundle(self,project="",machine="",limit_events=12):
        self.refresh_session_states()
        con=self.storage.connect()
        params=[]; where=[]
        if project: where.append("project=?"); params.append(project)
        if machine: where.append("machine=?"); params.append(machine)
        task_sql="SELECT * FROM tasks"
        if where: task_sql+=" WHERE "+" AND ".join(where)
        task_sql+=" ORDER BY updated_at DESC LIMIT 20"
        tasks=[dict(x) for x in con.execute(task_sql,params)]
        session_sql="SELECT * FROM sessions"
        if where: session_sql+=" WHERE "+" AND ".join(where)
        session_sql+=" ORDER BY heartbeat_at DESC LIMIT 20"
        sessions=[dict(x) for x in con.execute(session_sql,params)]
        events=[dict(x) for x in con.execute("SELECT * FROM events ORDER BY seq DESC LIMIT ?",(limit_events,))]
        con.close()
        return {
            "project":project,
            "machine":machine,
            "pending":[x for x in tasks if x["derived_state"]!="COMPLETED"],
            "sessions":sessions,
            "latest_handoff":self.latest_handoff(project,machine),
            "recent_events":list(reversed(events)),
        }


    def register_skill(self,skill_path,name,version="1.0.0",source_ref="",verified=False):
        path=Path(skill_path); manifest=path/"SKILL.md"
        if not manifest.is_file():
            raise ValueError("SKILL.md missing")
        content=manifest.read_bytes()
        digest=hashlib.sha256(content).hexdigest()
        sid=self._id("skill"); now=utc_now(); status="VERIFIED" if verified else "UNVERIFIED"
        con=self.storage.connect()
        old=con.execute("SELECT id,content_sha256,status FROM skills WHERE name=? AND version=?",(name,version)).fetchone()
        if old:
            if old["content_sha256"] != digest:
                con.close(); raise RuntimeError("skill version content changed; bump version")
            con.close()
            return self.get_skill(old["id"])
        con.execute("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?)",
                    (sid,name,version,str(path),source_ref,digest,status,now))
        con.commit(); con.close()
        return self.get_skill(sid)

    def get_skill(self,skill_id):
        con=self.storage.connect(); row=con.execute("SELECT * FROM skills WHERE id=?",(skill_id,)).fetchone(); con.close()
        if not row: raise KeyError(skill_id)
        return dict(row)

    def verify_skill(self,skill_id):
        skill=self.get_skill(skill_id)
        manifest=Path(skill["skill_path"])/"SKILL.md"
        if not manifest.is_file(): raise RuntimeError("skill disappeared")
        digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
        if digest != skill["content_sha256"]: raise RuntimeError("skill content changed after registration")
        con=self.storage.connect(); con.execute("UPDATE skills SET status='VERIFIED' WHERE id=?",(skill_id,)); con.commit(); con.close()
        return self.get_skill(skill_id)

    def activate_skill(self,skill_id,project="",machine=""):
        skill=self.get_skill(skill_id)
        if skill["status"]!="VERIFIED":
            raise RuntimeError("unverified skill cannot be activated")
        con=self.storage.connect()
        existing=con.execute("SELECT seq FROM skill_activations WHERE skill_id=? AND project=? AND machine=? AND active=1",
                             (skill_id,project,machine)).fetchone()
        if not existing:
            con.execute("INSERT INTO skill_activations(skill_id,project,machine,active,created_at) VALUES(?,?,?,?,?)",
                        (skill_id,project,machine,1,utc_now()))
            con.commit()
        con.close()
        return {"active":True,"skill_id":skill_id,"project":project,"machine":machine}

    def active_skills(self,project="",machine=""):
        con=self.storage.connect()
        rows=[dict(x) for x in con.execute(
            """SELECT s.* FROM skills s JOIN skill_activations a ON a.skill_id=s.id
               WHERE a.active=1 AND s.status='VERIFIED' AND a.project=? AND a.machine=?
               ORDER BY s.name,s.version""",(project,machine))]
        con.close(); return rows


    def register_process(self,name,cwd,argv,project="",machine="",readback=None,enabled=False):
        pid=self._id("proc"); now=utc_now(); readback=readback or []
        con=self.storage.connect()
        old=con.execute("SELECT * FROM process_specs WHERE name=?",(name,)).fetchone()
        if old:
            con.close(); return dict(old)
        con.execute("INSERT INTO process_specs VALUES(?,?,?,?,?,?,?,?,?)",
                    (pid,name,project,machine,str(cwd),json.dumps(argv,ensure_ascii=False),
                     json.dumps(readback,ensure_ascii=False),1 if enabled else 0,now))
        con.commit(); out=dict(con.execute("SELECT * FROM process_specs WHERE id=?",(pid,)).fetchone()); con.close()
        return out

    def get_process(self,process_id):
        con=self.storage.connect(); row=con.execute("SELECT * FROM process_specs WHERE id=?",(process_id,)).fetchone(); con.close()
        if not row: raise KeyError(process_id)
        out=dict(row); out["argv"]=json.loads(out.pop("argv_json")); out["readback"]=json.loads(out.pop("readback_json"))
        return out

    def set_process_enabled(self,process_id,enabled):
        con=self.storage.connect(); cur=con.execute("UPDATE process_specs SET enabled=? WHERE id=?",(1 if enabled else 0,process_id))
        if cur.rowcount!=1:
            con.close(); raise KeyError(process_id)
        con.commit(); con.close()
        return self.get_process(process_id)

    def _run_process_command(self,spec,timeout_seconds):
        return subprocess.run(
            spec["argv"],cwd=spec["cwd"],capture_output=True,text=True,
            encoding="utf-8",errors="replace",timeout=timeout_seconds,check=False
        )

    def _process_readback(self,spec):
        checks=[]
        for item in spec["readback"]:
            kind=item.get("kind")
            path=item.get("path","")
            if kind=="path_exists":
                ok=Path(path).exists()
                checks.append({"kind":kind,"path":path,"ok":ok})
                continue
            if kind=="path_nonempty":
                q=Path(path); ok=q.exists() and q.stat().st_size>0
                checks.append({"kind":kind,"path":path,"ok":ok})
                continue
            checks.append({"kind":kind,"ok":False,"error":"unsupported readback"})
        return checks

    def _record_process_timeout(self,task,session_id,timeout_seconds,exc):
        stdout=(exc.stdout or "")[-4000:] if isinstance(exc.stdout,str) else ""
        stderr=(exc.stderr or "")[-4000:] if isinstance(exc.stderr,str) else ""
        details={"timeout":timeout_seconds,"stdout_tail":stdout,"stderr_tail":stderr}
        self.add_event(task["id"],"PROCESS_TIMEOUT","EXECUTED","process timed out",session_id,details)
        return {"task_id":task["id"],"status":"TIMEOUT",**details}

    def execute_process(self,process_id,session_id,timeout_seconds=120,dry_run=False):
        spec=self.get_process(process_id)
        if dry_run:
            return {"dry_run":True,"cwd":spec["cwd"],"argv":spec["argv"],"readback":spec["readback"],"enabled":bool(spec["enabled"])}
        if not spec["enabled"]:
            raise RuntimeError("process disabled")
        task=self.create_task(
            f"execute:{spec['name']}",f"Execute process {spec['name']}",
            spec["project"],spec["machine"],session_id,"P1"
        )["task"]
        run_key=f"process:{process_id}:{task['id']}"
        self.begin_side_effect(
            task["id"],run_key,f"launch process {spec['name']}",session_id=session_id,
            details={"cwd":spec["cwd"],"argv":spec["argv"]}
        )
        try:
            completed=self._run_process_command(spec,timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            return self._record_process_timeout(task,session_id,timeout_seconds,exc)

        details={"returncode":completed.returncode,"stdout_tail":completed.stdout[-4000:],"stderr_tail":completed.stderr[-4000:]}
        self.record_side_effect_outcome(
            task["id"],run_key,f"process exited {completed.returncode}",
            session_id=session_id,details=details
        )
        checks=self._process_readback(spec)
        observed=all(x["ok"] for x in checks) if checks else completed.returncode==0
        self.reconcile_from_readback(task["id"],run_key,observed,{"checks":checks,"returncode":completed.returncode})
        if observed and completed.returncode==0:
            self.verify_e2e(task["id"],f"process {spec['name']} completed and read-back passed")
        return {
            "task_id":task["id"],"returncode":completed.returncode,"readback":checks,
            "derived_state":self.get_task(task["id"])["task"]["derived_state"]
        }

    def import_process_catalog(self,catalog_path):
        data=json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        imported=[]
        for spec in data.get("processes",[]):
            imported.append(self.register_process(
                spec["name"],spec["cwd"],spec["argv"],spec.get("project",""),spec.get("machine",""),
                spec.get("readback",[]),spec.get("enabled",False)))
        return imported


    def _create_alert(self,kind,severity,message,session_id=None,task_id=None,details=None):
        aid=self._id("alert"); con=self.storage.connect()
        con.execute("INSERT INTO alerts VALUES(?,?,?,?,?,?,?,0,?)",
                    (aid,kind,severity,session_id,task_id,message,
                     json.dumps(details or {},ensure_ascii=False),utc_now()))
        con.commit(); con.close()
        return aid

    def supervisor_tick(self,active_seconds=900,crash_seconds=3600,now=None):
        current=now or datetime.now(timezone.utc)
        con=self.storage.connect(); transitions=[]; crashes=[]
        rows=con.execute("SELECT * FROM sessions WHERE ended_at IS NULL").fetchall()
        for row in rows:
            beat=datetime.fromisoformat(row["heartbeat_at"])
            age=(current-beat).total_seconds()
            if age <= active_seconds:
                target="ACTIVE"
            elif age <= crash_seconds:
                target="IDLE"
            else:
                target="CRASHED"
            if row["status"]==target:
                continue
            if target=="CRASHED":
                con.execute("UPDATE sessions SET status='CRASHED',ended_at=? WHERE id=?",(current.isoformat(),row["id"]))
                owned=con.execute(
                    "SELECT id FROM tasks WHERE owner_session_id=? AND derived_state!='COMPLETED'",
                    (row["id"],)
                ).fetchall()
                for task in owned:
                    con.execute("UPDATE tasks SET derived_state='ORPHANED',updated_at=? WHERE id=?",
                                (current.isoformat(),task["id"]))
                    crashes.append({"session_id":row["id"],"task_id":task["id"],"age_seconds":age})
            else:
                con.execute("UPDATE sessions SET status=? WHERE id=?",(target,row["id"]))
            transitions.append({"session_id":row["id"],"from":row["status"],"to":target,"age_seconds":age})
        con.commit(); con.close()
        for item in crashes:
            self._create_alert(
                "ORPHANED_WORK","P0","Session heartbeat expired; unfinished work orphaned",
                item["session_id"],item["task_id"],{"age_seconds":item["age_seconds"]}
            )
        return {"transitions":transitions,"orphaned":crashes}

    def list_alerts(self,unacknowledged_only=True):
        con=self.storage.connect()
        sql="SELECT * FROM alerts"
        if unacknowledged_only:
            sql+=" WHERE acknowledged=0"
        sql+=" ORDER BY created_at DESC"
        rows=[dict(x) for x in con.execute(sql)]
        con.close()
        for row in rows:
            row["details"]=json.loads(row.pop("details_json"))
        return rows

    def acknowledge_alert(self,alert_id):
        con=self.storage.connect(); cur=con.execute("UPDATE alerts SET acknowledged=1 WHERE id=?",(alert_id,))
        if cur.rowcount!=1:
            con.close(); raise KeyError(alert_id)
        con.commit(); con.close()
        return {"acknowledged":True,"alert_id":alert_id}

    def status_snapshot(self,project="",machine=""):
        return {
            "health":self.health(),
            "context":self.context_bundle(project,machine,limit_events=8),
            "alerts":self.list_alerts(),
            "recovery":self.recovery_plan(),
        }

    def unresolved_side_effects(self):
        con=self.storage.connect(); rows=[dict(x) for x in con.execute("SELECT * FROM side_effects WHERE status='INTENT_RECORDED'")]; con.close(); return rows
    def pending(self):
        con=self.storage.connect(); rows=[dict(x) for x in con.execute("SELECT * FROM tasks WHERE derived_state!='COMPLETED'")]; con.close(); return rows
    def search(self,q):
        con=self.storage.connect(); rows=[dict(x) for x in con.execute("SELECT entity_type,entity_id,title,body,project,machine FROM search_index WHERE search_index MATCH ?",(q,))]; con.close(); return rows
    def health(self):
        con=self.storage.connect(); out={t:con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("sessions","tasks","events","side_effects","task_claims","handoffs","recovery_checks","skills","skill_activations","process_specs","alerts")}; con.close(); return {"ok":True,**out}
