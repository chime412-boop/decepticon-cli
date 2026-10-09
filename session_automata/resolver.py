from __future__ import annotations
import inspect
from typing import Any, Callable
from .core import SessionAutomata, PROVIDER_URLS

MaybeAsync = Callable[..., Any]

async def _call(fn: MaybeAsync, *args, **kwargs):
    value=fn(*args,**kwargs)
    if inspect.isawaitable(value):
        return await value
    return value

def _usable(a: SessionAutomata, result: dict[str,Any]|None)->bool:
    if not result or not result.get("ok"):
        return False
    url=str(result.get("url") or "")
    if url and a.is_protected(url):
        return False
    if result.get("loading") is True:
        return False
    if result.get("renderReady") is False:
        return False
    if result.get("engineReady") is False:
        return False
    return True

def _ready(provider, source, view, candidate=None, lease_id=None):
    out={"ok":True,"provider":provider,"source":source,"view":view,"lease_id":lease_id}
    if candidate is not None:
        out["profile"]=candidate
    return out

async def _probe_ready(a, provider, probe):
    view=await _call(probe,provider)
    return view if _usable(a,view) else None

async def _attempt_candidate(
    automata: SessionAutomata,
    provider: str,
    owner: str,
    candidate: dict[str,Any],
    probe: MaybeAsync,
    recover: MaybeAsync,
    launch: MaybeAsync,
    lease_ttl: int,
)->dict[str,Any]:
    pid=candidate["id"]
    lease=automata.acquire(provider,pid,owner,lease_ttl)
    if not lease:
        return {"ok":False,"failure":{"profile":candidate["alias"],"step":"lease","error":"BUSY"}}

    try:
        recovered=await _call(recover,provider,candidate)
        automata.record_attempt(provider,pid,"recover",bool(recovered and recovered.get("ok")),recovered or {})
        view=await _probe_ready(automata,provider,probe)
        if view:
            automata.record_attempt(provider,pid,"probe",True,view)
            return _ready(provider,"recover",view,candidate,lease)

        target=PROVIDER_URLS[provider]
        opened=await _call(launch,provider,candidate,target)
        automata.record_attempt(provider,pid,"launch",bool(opened and opened.get("ok")),opened or {})
        if not opened or not opened.get("ok"):
            automata.release(lease)
            return {"ok":False,"failure":{"profile":candidate["alias"],"step":"launch","error":str((opened or {}).get("error") or "FAILED")}}

        recovered=await _call(recover,provider,candidate)
        automata.record_attempt(provider,pid,"recover_after_launch",bool(recovered and recovered.get("ok")),recovered or {})
        view=await _probe_ready(automata,provider,probe)
        if view:
            automata.record_attempt(provider,pid,"probe",True,view)
            return _ready(provider,"launch_recover",view,candidate,lease)

        automata.record_attempt(provider,pid,"probe",False,{})
        automata.release(lease)
        return {"ok":False,"failure":{"profile":candidate["alias"],"step":"probe","error":"VIEW_NOT_READY"}}
    except Exception as exc:
        automata.record_attempt(provider,pid,"exception",False,{"error":f"{type(exc).__name__}:{exc}"})
        automata.release(lease)
        return {"ok":False,"failure":{"profile":candidate["alias"],"step":"exception","error":str(exc)}}

async def ensure_provider_view(
    automata: SessionAutomata,
    provider: str,
    owner: str,
    probe: MaybeAsync,
    recover: MaybeAsync,
    launch: MaybeAsync,
    *,
    lease_ttl: int=180,
)->dict[str,Any]:
    provider=str(provider).strip().lower()
    if provider not in PROVIDER_URLS:
        return {"ok":False,"error":"UNSUPPORTED_PROVIDER","provider":provider}

    existing=await _probe_ready(automata,provider,probe)
    if existing:
        return _ready(provider,"existing",existing)

    failures=[]
    for candidate in automata.candidates(provider):
        result=await _attempt_candidate(
            automata,provider,owner,candidate,probe,recover,launch,lease_ttl
        )
        if result.get("ok"):
            return result
        failures.append(result["failure"])

    return {"ok":False,"provider":provider,"error":"NO_READY_PROVIDER_VIEW","failures":failures}
