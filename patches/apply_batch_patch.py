#!/usr/bin/env python3
"""
apply_batch_patch.py — OpenClaw Batch API toggle patch (2026-07-23)
Run from the openclaw directory:
    python3 apply_batch_patch.py

Makes targeted changes to openclaw_core.py, openclaw_intake.py, and
openclaw_mission_control.py. Backs up originals before touching them.
"""
import shutil, sys, re
from pathlib import Path

BASE = Path(__file__).parent
errors = []

def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_batch")
    shutil.copy2(path, bak)
    print(f"  backed up → {bak.name}")

def patch(path, old, new, label):
    src = path.read_text()
    if old not in src:
        errors.append(f"PATCH MISS — {path.name}: '{label}' anchor not found")
        return False
    path.write_text(src.replace(old, new, 1))
    print(f"  ✓ {label}")
    return True

# ── openclaw_core.py ────────────────────────────────────────────────────────
print("\n[1/3] Patching openclaw_core.py ...")
core = BASE / "openclaw_core.py"
backup(core)

patch(core,
"def evaluation_agent(prop):\n    log(\"Evaluation\",",
"""def evaluation_agent(prop, _precomputed_eval_text=None,
                     _precomputed_stop_reason=None, _precomputed_usage=None):
    \"\"\"Batch API path (v1.1): when _precomputed_eval_text is provided the
    call_model() step is skipped and the supplied text is used as the model
    response. All downstream logic runs identically. Zero behavior change
    when params are None (default) — every existing call site unaffected.\"\"\"
    log(\"Evaluation\",""",
"evaluation_agent signature")

patch(core,
"    _eval_trace_id_box = []\n    result, stop_reason, usage = call_model(MODEL_SONNET, MASTER_PROMPT, content,\n                         temperature=0.2, max_tokens=EVAL_MAX_TOKENS, enable_cache=True,\n                         return_stop_reason=True,\n                         eval_id=prop.get(\"eval_id\"), step_type=\"evaluation\",\n                         trace_id_out=_eval_trace_id_box)\n    if not result:\n        return None",
"""    _eval_trace_id_box = []
    if _precomputed_eval_text is not None:
        result      = _precomputed_eval_text
        stop_reason = _precomputed_stop_reason or "end_turn"
        usage       = _precomputed_usage or {}
        log("Evaluation", f"[BATCH] precomputed text ({len(result)} chars)")
    else:
        result, stop_reason, usage = call_model(MODEL_SONNET, MASTER_PROMPT, content,
                             temperature=0.2, max_tokens=EVAL_MAX_TOKENS, enable_cache=True,
                             return_stop_reason=True,
                             eval_id=prop.get("eval_id"), step_type="evaluation",
                             trace_id_out=_eval_trace_id_box)
    if not result:
        return None""",
"evaluation_agent precomputed branch")

BATCH_FUNCS = '''

# ================================================================
# BATCH API HELPERS (v1.1, 2026-07-23)
# prepare_batch_prop  — everything UP TO evaluation_agent()
# finalize_batch_evaluation — everything FROM evaluation_agent() onward
# ================================================================

def prepare_batch_prop(kind, payload, dates, weights):
    """Pre-evaluation phase for batch. Returns (prop, content_str) or raises ValueError."""
    import re as _re
    prop = None
    if kind == "image":
        b64 = payload["b64"]
        media_type = payload.get("media_type", "image/png")
        parse_result = call_model(MODEL_SONNET, SCREENSHOT_PARSE_PROMPT,
            [{"type":"image","source":{"type":"base64","media_type":media_type,"data":b64}},
             {"type":"text","text":"Extract all props from this PrizePicks screenshot."}],
            temperature=0.1, max_tokens=800)
        if not parse_result:
            raise ValueError("could not read the screenshot — send a clearer image")
        try:
            parsed = json.loads(_re.sub(r"```json|```","",parse_result).strip())
        except Exception:
            raise ValueError("screenshot could not be parsed as JSON")
        if not parsed:
            raise ValueError("no props found in the screenshot")
        first_player = parsed[0].get("player")
        first_opponent = parsed[0].get("opponent")
        ctx = resolve_tournament_context(first_player, first_opponent) if first_player else None
        if not ctx:
            raise ValueError(f"could not confirm tournament for {first_player}")
        surface = ctx["surface"]; tour = ctx["tour"]; tournament = ctx["tournament"]
        is_gs = any(gs in tournament.lower() for gs in
                    ("wimbledon","us open","australian open","roland garros","french open"))
        for p in parsed:
            stat = normalize_stat_type(p.get("stat_type",""))
            pt = p.get("prop_type","standard")
            if p.get("is_demon") or pt == "demon":
                raise ValueError(f"DEMON prop skipped: {p.get('player')} {stat}")
            if stat.lower() in ("fantasy_score","fantasy score"):
                raise ValueError(f"Fantasy Score skip: {p.get('player')}")
            prop = {**p,"stat_type":stat,"tournament":tournament,"surface":surface,
                    "tour":tour,"tournament_stage":3 if is_gs else 1,"is_grand_slam":is_gs,
                    "both_directions_available":p.get("prop_type")=="standard",
                    "match_date":dates["match_date"],"same_day_3set_count":0}
            break
        if not prop:
            raise ValueError("no evaluable props found")
    elif kind == "text":
        user_input = payload.get("text","").strip()
        parts = user_input.split()
        if len(parts) < 3:
            raise ValueError("format: Player MORE/LESS LINE STAT")
        first_player = " ".join(parts[:-3]) if len(parts) > 4 else parts[0]
        ctx = resolve_tournament_context(first_player, None)
        surface = ctx["surface"] if ctx else "hard"
        tour = ctx["tour"] if ctx else "atp"
        tournament = ctx["tournament"] if ctx else "Current tournament"
        is_gs = any(gs in tournament.lower() for gs in
                    ("wimbledon","us open","australian open","roland garros","french open")) if ctx else False
        stat = normalize_stat_type(parts[-1])
        prop = {"player":first_player,"opponent":"Research required","stat_type":stat,
                "line":float(parts[-2]) if parts[-2].replace(".","").isdigit() else 0,
                "direction":parts[-3].upper() if parts[-3].upper() in ("LESS","MORE") else "LESS",
                "tournament":tournament,"surface":surface,"tour":tour,
                "tournament_stage":3 if is_gs else 1,"is_grand_slam":is_gs,
                "both_directions_available":True,"prop_type_classified":"standard",
                "match_date":dates["match_date"],"same_day_3set_count":0}
    else:
        raise ValueError(f"unsupported batch kind: {kind!r}")
    eval_id = d1.new_eval_id()
    prop["eval_id"] = eval_id
    d1.start(eval_id,"PROP",prop.get("player",""),prop.get("opponent",""),
             tour=prop.get("tour"),tournament=prop.get("tournament"),
             surface=prop.get("surface"),match_scheduled_time=prop.get("match_date"),
             market=prop.get("stat_type"),line=prop.get("line"),
             pipeline_version=CORE_VERSION,_logger=log)
    if _V8_AVAILABLE:
        try:
            pkt = build_tennis_packet(prop.get("player",""),prop.get("opponent",""),
                                      prop.get("surface","hard"),prop.get("tour","atp"))
            if pkt:
                pkt["_prefetch_tour"] = prop.get("tour","atp")
                prop["_v8_packet_prefetched"] = pkt
        except Exception as e:
            log("BatchPrep",f"V8 pre-fetch failed (non-fatal): {e}")
    gate_result = gate_11_check(prop, dates)
    if gate_result["status"] == "REJECTED":
        d1.terminate(eval_id,"GATE11_REJECTED",_logger=log)
        raise ValueError(f"Gate 11 rejected: {gate_result.get('reason','not found in V8')}")
    if gate_result.get("verified") is False:
        prop["gate11_unverified"] = True
    prop = gate_11b_format_detection(prop)
    d1.transition(eval_id,"RESEARCH_STARTED",_logger=log)
    d1.heartbeat("research","WORKING",current_task=prop.get("player"),_logger=log)
    try:
        prop = research_agent(prop, dates)
    except Exception as e:
        d1.terminate(eval_id,"RESEARCH_FAILURE",str(e),_logger=log)
        d1.heartbeat("research","FAILED",detail=str(e),increment_failure=True,_logger=log)
        raise ValueError(f"Research failed: {e}")
    d1.transition(eval_id,"RESEARCH_COMPLETE",_logger=log)
    d1.heartbeat("research","IDLE",increment_success=True,_logger=log)
    content = build_evaluation_content(prop)
    log("BatchPrep",f"Prepared {prop.get('player')} {prop.get('stat_type')} — ready for batch")
    return prop, content


def finalize_batch_evaluation(prop, eval_text, stop_reason, dates, weights):
    """Post-evaluation phase for batch. Runs compliance→scoring→posting."""
    eval_id = prop.get("eval_id")
    pipeline_flags = prop.get("_pipeline_flags",[])
    d1.heartbeat("evaluation","WORKING",current_task=prop.get("player"),_logger=log)
    evaluated = evaluation_agent(prop,_precomputed_eval_text=eval_text,
                                  _precomputed_stop_reason=stop_reason,_precomputed_usage={})
    if not evaluated:
        d1.terminate(eval_id,"EVAL_ATTEMPTS_EXHAUSTED",_logger=log)
        send_discord("alerts",f"🛑 **BATCH EVAL FAILED** — {prop.get('player')} {prop.get('stat_type')}")
        return None
    if evaluated.get("_truncated"):
        d1.terminate(eval_id,"EVAL_TRUNCATED",str(evaluated.get("_truncation_diagnostics",{})),_logger=log)
        send_discord("alerts",f"🛑 **BATCH EVAL TRUNCATED** — {prop.get('player')} {prop.get('stat_type')}")
        return None
    d1.transition(eval_id,"EVALUATION_COMPLETE",direction=evaluated.get("direction"),
                   dominance_level=evaluated.get("dominance_level"),_logger=log)
    d1.heartbeat("evaluation","IDLE",increment_success=True,_logger=log)
    compliance_penalty = False; compliance_flags = []
    for attempt in range(1,3):
        d1.heartbeat("compliance","WORKING",current_task=prop.get("player"),_logger=log)
        audit = compliance_agent(evaluated, attempt)
        if audit["status"] == "APPROVED": break
        if audit["status"] == "ACCEPTED_WITH_PENALTY":
            compliance_penalty = True; compliance_flags = audit.get("flags",[]); break
        if audit["status"] == "FLAGGED_FOR_MANUAL_REVIEW":
            d1.terminate(eval_id,"COMPLIANCE_UNPARSEABLE",_logger=log)
            send_discord("alerts",f"🛑 **BATCH COMPLIANCE FAILED** — {evaluated.get('player')} {prop.get('stat_type')}")
            return None
        if audit["status"] == "FLAGGED" and attempt == 1:
            _a = [f for f in (audit.get("flags") or []) if f.get("category","A") != "B"]
            if not _a:
                compliance_penalty = True; compliance_flags = audit.get("flags",[]); break
            prop["compliance_flags"] = audit.get("flags",[]); prop["is_re_evaluation"] = True
            evaluated = evaluation_agent(prop)
            if not evaluated: break
        else:
            compliance_penalty = True; compliance_flags = audit.get("flags",[]); break
    if not evaluated:
        d1.terminate(eval_id,"EVAL_ATTEMPTS_EXHAUSTED",_logger=log); return None
    d1.transition(eval_id,"COMPLIANCE_COMPLETE",
                   compliance_category=("A" if any(f.get("category","A")=="A" for f in (compliance_flags or []))
                                        else ("B" if compliance_flags else None)),_logger=log)
    d1.heartbeat("compliance","IDLE",increment_success=True,_logger=log)
    scored = scoring_agent(evaluated, weights, compliance_penalty, compliance_flags, eval_id=eval_id)
    if scored.get("confidence") is None: return None
    scored.update({"eval_id":eval_id,"pipeline_flags":pipeline_flags,
                   "compliance_flags":compliance_flags,"compliance_penalty":compliance_penalty,
                   "evaluation_attempts":1,"match_date":dates["match_date"],
                   "pipeline_run_date":dates["pipeline_run_date"]})
    send_discord("picks",f"⏳ **BATCH RESULT** — {dates['ct_time']}\\n\\n{format_pick_card(scored,1)}")
    save_evaluation_reasoning(scored.get("player",prop.get("player","?")),
                               scored.get("opponent",prop.get("opponent","?")),
                               "props", scored.get("evaluation",json.dumps(scored,indent=2,default=str)), dates)
    return scored

'''

patch(core,
"# ================================================================\n# COMPLIANCE AGENT\n# ================================================================",
BATCH_FUNCS + "# ================================================================\n# COMPLIANCE AGENT\n# ================================================================",
"insert prepare_batch_prop + finalize_batch_evaluation")

# ── openclaw_intake.py ──────────────────────────────────────────────────────
print("\n[2/3] Patching openclaw_intake.py ...")
intake = BASE / "openclaw_intake.py"
backup(intake)

patch(intake,
'import json, threading, time, base64, traceback, datetime as dt\nfrom pathlib import Path',
'import json, threading, time, base64, traceback, datetime as dt, requests\nfrom pathlib import Path',
"add requests import")

patch(intake,
'def enqueue(kind, payload):\n    """kind=\'text\' -> payload={\'text\': \'Player MORE/LESS LINE STAT\'}\n       kind=\'image\'-> payload={\'b64\':..., \'media_type\':...}"""',
'def enqueue(kind, payload, batch_eligible=False):\n    """kind=\'text\' -> payload={\'text\': \'Player MORE/LESS LINE STAT\'}\n       kind=\'image\'-> payload={\'b64\':..., \'media_type\':...}\n       batch_eligible=True: defers the Sonnet eval call to the Batch API (50% off)."""\n    if kind == "ml_image" and batch_eligible:\n        batch_eligible = False  # moneyline always synchronous',
"enqueue batch_eligible param")

patch(intake,
'            "error": None}',
'            "error": None,\n            "batch_eligible": batch_eligible,\n            "batch_id": None,\n            "batch_custom_id": None,\n            "_batch_prop": None,\n        }',
"enqueue item batch fields")

patch(intake,
'def queue_view():\n    """Public, image bytes stripped — safe to serialize to the browser."""\n    return [{k: v for k, v in i.items() if k != "payload"} |',
'def queue_view():\n    """Public, image bytes and batch prop state stripped — safe to serialize to the browser."""\n    return [{k: v for k, v in i.items() if k not in ("payload","_batch_prop")} |',
"queue_view strip _batch_prop")

BATCH_SUBMIT = '''

def _process_batch_submit(item):
    """Pre-eval for batch: research+gates+content → submit to /v1/messages/batches."""
    dates = oc.get_system_dates(); weights = oc.load_weights()
    prop, content = oc.prepare_batch_prop(item["kind"], item["payload"], dates, weights)
    EVAL_MAX_TOKENS = 16000
    custom_id = f"intake-{item['id']}"
    batch_payload = {"requests":[{"custom_id":custom_id,"params":{
        "model":oc.MODEL_SONNET,"max_tokens":EVAL_MAX_TOKENS,"temperature":0.2,
        "system":[{"type":"text","text":oc.MASTER_PROMPT,
                   "cache_control":{"type":"ephemeral","ttl":"1h"}}],
        "messages":[{"role":"user","content":content}]}}]}
    resp = requests.post("https://api.anthropic.com/v1/messages/batches",
        headers={"x-api-key":oc.ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01",
                 "content-type":"application/json"},
        json=batch_payload, timeout=30)
    if resp.status_code != 200:
        raise ValueError(f"Batch API error: HTTP {resp.status_code} — {resp.text[:200]}")
    anthropic_batch_id = resp.json().get("id","")
    if not anthropic_batch_id:
        raise ValueError(f"Batch API returned no id: {resp.text[:200]}")
    prop_snapshot = {k:v for k,v in prop.items() if k != "_v8_packet_prefetched"}
    _set(item["id"], status="BATCH_PENDING", batch_id=anthropic_batch_id,
         batch_custom_id=custom_id, _batch_prop=prop_snapshot,
         submitted_at=dt.datetime.now(oc.CT).strftime("%I:%M %p").lstrip("0"))
    oc.log("Batch", f"#{item['id']} ({item['label']}) → batch {anthropic_batch_id}")


def _batch_poller():
    """Background thread: checks every 10 min for completed batches, finalizes results."""
    CHECK_INTERVAL = 600
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            q = _load()
            pending = [i for i in q if i.get("status")=="BATCH_PENDING" and i.get("batch_id")]
            if not pending: continue
            batches = {}
            for item in pending: batches.setdefault(item["batch_id"],[]).append(item)
            dates = oc.get_system_dates(); weights = oc.load_weights()
            for batch_id, items in batches.items():
                try:
                    sr = requests.get(f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
                        headers={"x-api-key":oc.ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
                        timeout=30)
                except Exception as e:
                    oc.log("Batch",f"Status check error for {batch_id}: {e}"); continue
                if sr.status_code != 200: continue
                if sr.json().get("processing_status") != "ended":
                    oc.log("Batch",f"{batch_id[:20]}… still processing"); continue
                try:
                    rr = requests.get(f"https://api.anthropic.com/v1/messages/batches/{batch_id}/results",
                        headers={"x-api-key":oc.ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
                        timeout=60)
                except Exception as e:
                    oc.log("Batch",f"Results fetch error: {e}"); continue
                if rr.status_code != 200: continue
                results_by_id = {}
                for line in rr.text.strip().split("\\n"):
                    if not line.strip(): continue
                    try:
                        row = json.loads(line); results_by_id[row["custom_id"]] = row
                    except Exception: pass
                for item in items:
                    custom_id = item.get("batch_custom_id")
                    row = results_by_id.get(custom_id)
                    if not row: continue
                    rb = row.get("result",{})
                    if rb.get("type") != "succeeded":
                        err = rb.get("error",{})
                        _set(item["id"],status="FAILED",
                             error=f"Batch error: {err.get('type','?')} — {err.get('message','')[:200]}",
                             finished_at=dt.datetime.now(oc.CT).strftime("%I:%M %p").lstrip("0"))
                        continue
                    msg = rb.get("message",{}); blk = (msg.get("content") or [{}])[0]
                    eval_text = blk.get("text",""); stop_reason = msg.get("stop_reason","end_turn")
                    if not eval_text:
                        _set(item["id"],status="FAILED",error="Batch result empty"); continue
                    prop = item.get("_batch_prop")
                    if not prop:
                        _set(item["id"],status="FAILED",error="prop state lost"); continue
                    _set(item["id"],status="RUNNING",
                         started_at=dt.datetime.now(oc.CT).strftime("%I:%M %p").lstrip("0"))
                    try:
                        oc.finalize_batch_evaluation(prop,eval_text,stop_reason,dates,weights)
                        _set(item["id"],status="DONE",
                             finished_at=dt.datetime.now(oc.CT).strftime("%I:%M %p").lstrip("0"))
                    except Exception as e:
                        oc.log("Batch",f"finalize failed #{item['id']}: {e}")
                        _set(item["id"],status="FAILED",error=str(e)[:300],
                             finished_at=dt.datetime.now(oc.CT).strftime("%I:%M %p").lstrip("0"))
        except Exception:
            oc.log("Batch","poller error: "+traceback.format_exc()[:300]); time.sleep(60)

'''

patch(intake,
"def _worker():",
BATCH_SUBMIT + "def _worker():",
"insert _process_batch_submit + _batch_poller")

patch(intake,
"            try:\n                _process(nxt)\n                _set(nxt[\"id\"], status=\"DONE\",\n                     finished_at=dt.datetime.now(oc.CT).strftime(\"%I:%M %p\").lstrip(\"0\"))\n            except Exception as e:\n                oc.log(\"Intake\", f\"eval failed for #{nxt['id']}: {e}\")\n                _set(nxt[\"id\"], status=\"FAILED\", error=str(e)[:300])",
"""            try:
                if nxt.get("batch_eligible"):
                    _process_batch_submit(nxt)
                else:
                    _process(nxt)
                    _set(nxt["id"], status="DONE",
                         finished_at=dt.datetime.now(oc.CT).strftime("%I:%M %p").lstrip("0"))
            except Exception as e:
                oc.log("Intake", f"eval failed for #{nxt['id']}: {e}")
                _set(nxt["id"], status="FAILED", error=str(e)[:300])""",
"worker batch routing")

patch(intake,
'    threading.Thread(target=_worker, daemon=True, name="intake-worker").start()\n    oc.log("Intake", "Mission Control intake worker started")',
'    threading.Thread(target=_worker, daemon=True, name="intake-worker").start()\n    threading.Thread(target=_batch_poller, daemon=True, name="batch-poller").start()\n    oc.log("Intake", "Mission Control intake worker + batch poller started")',
"start_worker launch poller")

# ── openclaw_mission_control.py ─────────────────────────────────────────────
print("\n[3/3] Patching openclaw_mission_control.py ...")
mc = BASE / "openclaw_mission_control.py"
backup(mc)

patch(mc,
'            elif self.path == "/api/intake/text":\n                iid = intake.enqueue("text", {"text": body["text"].strip()})',
'''            elif self.path == "/api/intake/batch_text":
                iid = intake.enqueue("text",{"text":body["text"].strip()},batch_eligible=True)
                return self._send(200,{"ok":True,"id":iid})
            elif self.path == "/api/intake/batch_image":
                b64=body.get("b64","")
                iid = intake.enqueue("image",{"b64":b64,"media_type":body.get("media_type","image/png")},batch_eligible=True)
                return self._send(200,{"ok":True,"id":iid})
            elif self.path == "/api/intake/text":
                iid = intake.enqueue("text", {"text": body["text"].strip()})''',
"MC batch routes")

patch(mc,
' const mtr={QUEUED:0,RUNNING:0,DONE:0,FAILED:0};q.forEach(i=>mtr[i.status]=(mtr[i.status]||0)+1);',
' const mtr={QUEUED:0,RUNNING:0,DONE:0,FAILED:0,BATCH_PENDING:0};q.forEach(i=>mtr[i.status]=(mtr[i.status]||0)+1);',
"MC mtr BATCH_PENDING")

patch(mc,
" const filterMap={ALL:null,WAITING:'QUEUED',RUNNING:'RUNNING',COMPLETED:'DONE',FAILED:'FAILED'};",
" const filterMap={ALL:null,WAITING:'QUEUED',RUNNING:'RUNNING',COMPLETED:'DONE',FAILED:'FAILED',BATCH:'BATCH_PENDING'};",
"MC filterMap BATCH")

patch(mc,
"  <div class=\"tile\"><div class=\"t\">FAILED</div><div class=\"v\" style=\"color:${mtr.FAILED?'var(--red)':'inherit'}\">${mtr.FAILED}</div></div></div>\n <div style=\"margin-bottom:12px\">${tab('ALL','All',q.length)} ${tab('WAITING','Waiting',mtr.QUEUED)} ${tab('RUNNING','Running',mtr.RUNNING)} ${tab('COMPLETED','Completed',mtr.DONE)} ${tab('FAILED','Failed',mtr.FAILED)}</div>",
"  <div class=\"tile\"><div class=\"t\">FAILED</div><div class=\"v\" style=\"color:${mtr.FAILED?'var(--red)':'inherit'}\">${mtr.FAILED}</div></div>\n  <div class=\"tile\"><div class=\"t\">⏳ BATCH</div><div class=\"v\" style=\"color:${mtr.BATCH_PENDING?'#f5c542':'inherit'}\">${mtr.BATCH_PENDING}</div></div></div>\n <div style=\"margin-bottom:12px\">${tab('ALL','All',q.length)} ${tab('WAITING','Waiting',mtr.QUEUED)} ${tab('RUNNING','Running',mtr.RUNNING)} ${tab('COMPLETED','Completed',mtr.DONE)} ${tab('FAILED','Failed',mtr.FAILED)} ${tab('BATCH','⏳ Batch',mtr.BATCH_PENDING)}</div>",
"MC BATCH tile + tab")

patch(mc,
"  <input id=\"tx\" style=\"width:70%\" placeholder=\"Player MORE/LESS LINE STAT\">\n  <button onclick=\"subText()\">submit to OpenClaw</button></div>",
"  <input id=\"tx\" style=\"width:70%\" placeholder=\"Player MORE/LESS LINE STAT\">\n  <button onclick=\"subText()\">evaluate now</button>\n  <button onclick=\"subTextBatch()\" style=\"margin-left:6px;border:1px solid #f5c542;color:#f5c542\">⏳ queue for batch</button></div>",
"MC text batch button")

patch(mc,
"  <input type=\"file\" id=\"img\" accept=\"image/*\" style=\"width:auto\" onchange=\"subImg()\">\n  <button onclick=\"subImg()\">upload & submit</button> <span id=\"imgStatus\" class=\"m\"></span>\n  <div class=\"m\">runs the same screenshot→research→pipeline path as #general, from here.</div></div>",
"  <div class=\"m\">Evaluate now — auto-submits on select:</div>\n  <input type=\"file\" id=\"img\" accept=\"image/*\" style=\"width:auto\" onchange=\"subImg()\">\n  <span id=\"imgStatus\" class=\"m\"></span>\n  <div class=\"m\" style=\"margin-top:8px\">⏳ Queue for batch (50% off, ~2-8h):</div>\n  <input type=\"file\" id=\"imgBatch\" accept=\"image/*\" style=\"width:auto\">\n  <button onclick=\"subImgBatch()\" style=\"border:1px solid #f5c542;color:#f5c542\">⏳ queue for batch</button>\n  <span id=\"imgBatchStatus\" class=\"m\"></span></div>",
"MC screenshot batch input")

patch(mc,
"async function subText(){const t=document.getElementById('tx').value.trim();if(!t)return;\n await fetch('/api/intake/text',{method:'POST',body:JSON.stringify({text:t})});\n document.getElementById('tx').value='';load()}",
"""async function subText(){const t=document.getElementById('tx').value.trim();if(!t)return;
 await fetch('/api/intake/text',{method:'POST',body:JSON.stringify({text:t})});
 document.getElementById('tx').value='';load()}
async function subTextBatch(){const t=document.getElementById('tx').value.trim();if(!t)return;
 await fetch('/api/intake/batch_text',{method:'POST',body:JSON.stringify({text:t})});
 document.getElementById('tx').value='';load()}
async function subImgBatch(){
 const el=document.getElementById('imgBatch');const f=el&&el.files[0];if(!f)return;
 const st=()=>document.getElementById('imgBatchStatus');
 if(st())st().textContent='uploading '+f.name+'...';
 try{
  const b64=await new Promise((r,j)=>{const rd=new FileReader();rd.onload=()=>r(rd.result);rd.onerror=()=>j(rd.error);rd.readAsDataURL(f)});
  const resp=await fetch('/api/intake/batch_image',{method:'POST',body:JSON.stringify({b64,media_type:f.type||'image/png'})});
  if(!resp.ok)throw new Error('HTTP '+resp.status);
  const d=await resp.json();
  if(st())st().textContent='queued as #'+d.id+' ⏳ (result ~2-8h)';
 }catch(e){if(st())st().textContent='FAILED: '+e;}
 load()}""",
"MC subTextBatch + subImgBatch JS")

patch(mc,
"   <td><span class=\"chip ${i.status=='DONE'?'ok':i.status=='FAILED'?'A':''}\">${i.status}</span></td>",
"   <td><span class=\"chip ${i.status=='DONE'?'ok':i.status=='FAILED'?'A':''}\" style=\"${i.status=='BATCH_PENDING'?'color:#f5c542;border-color:#f5c542':''}\">${i.status=='BATCH_PENDING'?'⏳ BATCH':i.status}</span></td>",
"MC BATCH badge in queue table")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "="*60)
if errors:
    print(f"⚠️  {len(errors)} patch(es) MISSED — verify before deploying:")
    for e in errors: print(f"  {e}")
    sys.exit(1)
else:
    print("✅ All patches applied. Verify hashes:")
    import hashlib
    for f in [BASE/"openclaw_intake.py", BASE/"openclaw_core.py", BASE/"openclaw_mission_control.py"]:
        h = hashlib.sha1(f.read_bytes()).hexdigest()[:8]
        print(f"  {h}  {f.name}")
    print("\nThen restart both agents and confirm in Mission Control.")
