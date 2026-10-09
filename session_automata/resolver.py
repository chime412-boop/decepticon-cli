from __future__ import annotations
import inspect
from typing import Any, Awaitable, Callable
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

    first=await _call(probe,provider)
    if _usable(automata,first):
        return {"ok":True,"provider":provider,"source":"existing","view":first,"lease_id":None}

    failures=[]
    for candidate in automata.candidates(provider):
        pid=candidate["id"]
        lease=automata.acquire(provider,pid,owner,lease_ttl)
        if not lease:
            failures.append({"profile":candidate["alias"],"step":"lease","error":"BUSY"})
            continue
        try:
            rec=await _call(recover,provider,candidate)
            automata.record_attempt(provider,pid,"recover",bool(rec and rec.get("ok")),rec or {})
            post=await _call(probe,provider)
            if _usable(automata,post):
                automata.record_attempt(provider,pid,"probe",True,post)
                return {"ok":True,"provider":provider,"source":"recover","profile":candidate,
                        "lease_id":lease,"view":post}

            target=PROVIDER_URLS[provider]
            opened=await _call(launch,provider,candidate,target)
            automata.record_attempt(provider,pid,"launch",bool(opened and opened.get("ok")),opened or {})
            if not opened or not opened.get("ok"):
                failures.append({"profile":candidate["alias"],"step":"launch","error":str((opened or {}).get("error") or "FAILED")})
                automata.release(lease); continue

            rec2=await _call(recover,provider,candidate)
            automata.record_attempt(provider,pid,"recover_after_launch",bool(rec2 and rec2.get("ok")),rec2 or {})
            post2=await _call(probe,provider)
            if _usable(automata,post2):
                automata.record_attempt(provider,pid,"probe",True,post2)
                return {"ok":True,"provider":provider,"source":"launch_recover",
                        "profile":candidate,"lease_id":lease,"view":post2}

            automata.record_attempt(provider,pid,"probe",False,post2 or {})
            failures.append({"profile":candidate["alias"],"step":"probe","error":"VIEW_NOT_READY"})
            automata.release(lease)
        except Exception as exc:
            automata.record_attempt(provider,pid,"exception",False,{"error":f"{type(exc).__name__}:{exc}"})
            failures.append({"profile":candidate["alias"],"step":"exception","error":str(exc)})
            automata.release(lease)

    return {"ok":False,"provider":provider,"error":"NO_READY_PROVIDER_VIEW","failures":failures}
