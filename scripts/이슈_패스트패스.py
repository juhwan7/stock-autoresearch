#!/usr/bin/env python3
"""Discovery -> issue-digest fast path.

This path is deliberately conservative: it records newly observed news as
pending evidence without making Supervisor-only escalation/easing/resolution
judgements. It is idempotent by source URL and runs independently of A/B.
"""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT=Path(__file__).resolve().parents[1]
DISCOVERY=ROOT/"data/discovery/latest.json"
DIGEST=ROOT/"data/news/issue-digest.json"
STATE=ROOT/"data/news/fast-path-state.json"
MAX_ISSUES=100
MAX_EVENTS=120

def read(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError): return default

def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tmp.replace(path)

def canonical_url(raw):
    raw=str(raw or "").strip()
    if not raw: return ""
    try:
        p=urlsplit(raw)
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path,p.query,""))
    except ValueError: return raw

def event_time(raw):
    if not raw: return None
    try:
        d=parsedate_to_datetime(str(raw))
        return d.isoformat()
    except (TypeError,ValueError):
        try: return datetime.fromisoformat(str(raw).replace("Z","+00:00")).isoformat()
        except ValueError: return None

def slug(topic):
    value=re.sub(r"[^a-z0-9]+","-",str(topic or "").lower()).strip("-")
    return value or "discovery-"+hashlib.sha1(str(topic).encode()).hexdigest()[:10]

def title_for(topic,item):
    t=str(item.get("title") or "").strip()
    return t[:140] if t else str(topic).replace("_"," ")[:140]

def main():
    discovery=read(DISCOVERY,{})
    generated=str(discovery.get("generated_at") or "")
    items=[x for x in discovery.get("new_items",[]) if isinstance(x,dict)]
    store=read(DIGEST,{"schema_version":2,"issues":[]})
    state=read(STATE,{"schema_version":1,"processed_urls":[]})
    processed=set(state.get("processed_urls") or [])
    issues={str(x.get("issue_id")):x for x in store.get("issues",[]) if isinstance(x,dict) and x.get("issue_id")}
    added_events=0; added_sources=0
    for item in items:
        url=canonical_url(item.get("url"))
        if not url or url in processed: continue
        topic=str(item.get("topic") or "unclassified")
        iid="discovery-"+slug(topic)
        now=generated or datetime.now().astimezone().isoformat()
        published=event_time(item.get("published_at"))
        source={"publisher":str(item.get("publisher") or "unknown"),"title":str(item.get("title") or ""),"url":url,"published_at":published,"discovery_source":item.get("discovery_source")}
        issue=issues.get(iid)
        if issue is None:
            issue={"issue_id":iid,"title":title_for(topic,item),"scope":"UNKNOWN","category":topic,
                   "status":"WATCHING","verification_status":"pending","severity":"UNVERIFIED","impact":"UNVERIFIED",
                   "first_detected":now,"last_updated":now,"article_count":0,"independent_evidence_count":None,
                   "independent_evidence_status":"not_verified","sources":[],"history":[]}
            issues[iid]=issue
        urls={canonical_url(s.get("url")) for s in issue.get("sources",[]) if isinstance(s,dict)}
        if url in urls:
            processed.add(url); continue
        issue.setdefault("sources",[]).append(source)
        issue["sources"]=issue["sources"][-60:]
        issue["article_count"]=len(issue["sources"])
        issue["source_count"]=len({str(s.get("publisher") or "") for s in issue["sources"] if s.get("publisher")})
        issue["last_updated"]=now
        issue["verification_status"]="pending"
        issue["independent_evidence_count"]=None
        issue["independent_evidence_status"]="not_verified"
        event={"event_at":published,"observed_at":now,"status":issue.get("status","WATCHING"),
               "verification_status":"pending","event_type":"NEW" if len(issue["sources"])==1 else "NEW_EVIDENCE",
               "summary":str(item.get("title") or "")[:300],"source":source["publisher"],"source_url":url,
               "source_count":issue["source_count"],"independent_evidence_count":None,"confirmed":False,
               "created_by":"issue_fast_path"}
        issue.setdefault("history",[]).append(event)
        issue["history"]=issue["history"][-MAX_EVENTS:]
        processed.add(url); added_sources+=1; added_events+=1
    ordered=sorted(issues.values(),key=lambda x:str(x.get("last_updated") or ""),reverse=True)[:MAX_ISSUES]
    if generated:
        store["updated_at"]=generated
    store["schema_version"]=max(int(store.get("schema_version") or 1),2)
    store["issues"]=ordered
    store["max_issues"]=MAX_ISSUES
    store["fast_path"]={"last_attempt":datetime.now().astimezone().isoformat(),"last_success":generated or datetime.now().astimezone().isoformat(),
                        "discovery_generated_at":generated,"new_item_count":len(items),"added_sources":added_sources,
                        "added_events":added_events,"supervisor_required":False,
                        "semantics":"pending evidence only; escalation/easing/resolution remain Supervisor decisions"}
    write(DIGEST,store)
    state.update({"last_processed_discovery_at":generated,"last_success":datetime.now().astimezone().isoformat(),
                  "processed_urls":list(processed)[-5000:],"backlog":0,"added_events_last_run":added_events})
    write(STATE,state)
    print(json.dumps({"status":"ok","discovery":generated,"new_items":len(items),"added_events":added_events},ensure_ascii=False))
if __name__=="__main__": main()
