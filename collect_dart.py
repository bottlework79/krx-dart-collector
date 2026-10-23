"""Standalone incremental DART CFS collector. Public code; credentials in Actions secrets."""
import argparse
import concurrent.futures
import datetime as dt
import gzip
import io
import json
import os
import pickle
import tempfile
import time
import threading
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT=Path("data")
DB=ROOT/"financial_statements.pkl.gz"
MISSING=ROOT/"unavailable_periods.json"
REPORTS={"annual":"11011","q1":"11013","half":"11012","q3":"11014"}
API="https://opendart.fss.or.kr/api/"
THREAD_LOCAL=threading.local()

def session():
    s=requests.Session()
    retry=Retry(total=2,connect=2,read=1,status=2,backoff_factor=1,
                status_forcelist=[429,500,502,503,504],
                allowed_methods=frozenset(["GET"]),respect_retry_after_header=True)
    s.mount("https://",HTTPAdapter(max_retries=retry))
    return s

def worker_session():
    if not hasattr(THREAD_LOCAL,"session"):
        THREAD_LOCAL.session=session()
    return THREAD_LOCAL.session

def companies(key):
    with session() as s:
        r=s.get(API+"corpCode.xml",params={"crtfc_key":key},timeout=90)
        r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        with archive.open("CORPCODE.xml") as f:
            root=ET.parse(f).getroot()
    result={}
    for item in root.findall("list"):
        code=(item.findtext("stock_code") or "").strip()
        corp=(item.findtext("corp_code") or "").strip()
        if len(code)==6 and code.isdigit() and corp:
            result[code]={"corp_code":corp,"name":item.findtext("corp_name") or ""}
    return result

def load():
    if not DB.exists():return {}
    with gzip.open(DB,"rb") as f:db=pickle.load(f)
    if not isinstance(db,dict):raise ValueError("Invalid financial DB")
    return db

def save(db):
    ROOT.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=ROOT,delete=False,suffix=".tmp") as tmp:
        path=Path(tmp.name)
    try:
        with gzip.open(path,"wb",compresslevel=6) as f:
            pickle.dump(db,f,protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(path,DB)
    finally:
        path.unlink(missing_ok=True)

def request(key,corp,year,report):
    started=time.monotonic()
    s=worker_session()
    try:
        r=s.get(API+"fnlttSinglAcntAll.json",params={
            "crtfc_key":key,"corp_code":corp,"bsns_year":year,
            "reprt_code":REPORTS[report],"fs_div":"CFS"},timeout=(10,30))
        r.raise_for_status()
        payload=r.json()
    except Exception:
        print("DART_REQUEST_FAILURE="+json.dumps({"error_type":"request_failed","seconds":round(time.monotonic()-started,2)}),flush=True)
        raise
    status=payload.get("status")
    result=("unavailable",[]) if status=="013" else (("api_"+str(status),[]) if status!="000" else ("ok",payload.get("list",[])))
    print("DART_REQUEST_TIMING="+json.dumps({"seconds":round(time.monotonic()-started,2),"status":result[0]}),flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--batch-index",type=int,default=0)
    p.add_argument("--batch-size",type=int,default=2)
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--start-year",type=int,default=2021)
    p.add_argument("--end-year",type=int,default=dt.date.today().year)
    p.add_argument("--universe-file",default="data/krx_universe.json")
    p.add_argument("--missing-recheck-days",type=int,default=7)
    p.add_argument("--history-file",default=None,help="Only skip records confirmed imported in Private")
    args=p.parse_args()
    if args.batch_index<0 or not 1<=args.batch_size<=25 or not 1<=args.workers<=3:
        raise SystemExit("Invalid batch/workers")
    if args.start_year>args.end_year:raise SystemExit("Invalid year range")
    if not 1<=args.missing_recheck_days<=90:raise SystemExit("Invalid missing recheck days")
    key=os.environ.get("DART_API_KEY")
    if not key:raise SystemExit("Missing DART_API_KEY")
    mapping=companies(key)
    if not args.universe_file or not Path(args.universe_file).is_file():
        raise SystemExit("Required KRX universe snapshot missing")
    if args.universe_file:
        allowed=json.loads(Path(args.universe_file).read_text(encoding="utf-8"))
        if not isinstance(allowed,list) or not all(isinstance(x,str) and len(x)==6 and x.isdigit() for x in allowed):
            raise SystemExit("Invalid public ticker universe file")
        tickers=sorted(set(allowed)&set(mapping))
        print("KRX_UNIVERSE_MATCH="+json.dumps({"snapshot":len(set(allowed)),"dart_matched":len(tickers),"unmatched":len(set(allowed)-set(mapping))}))
    else:
        raise SystemExit("KRX universe snapshot required; refusing unbounded DART collection")
    start=args.batch_index*args.batch_size
    selected=tickers[start:start+args.batch_size]
    if not selected:raise SystemExit("Empty batch")
    if not args.universe_file or not Path(args.universe_file).exists():
        raise SystemExit("Missing KRX universe file; do not collect full DART universe")
    db=load()
    if MISSING.exists():
        raw_missing=json.loads(MISSING.read_text(encoding="utf-8"))
        if isinstance(raw_missing,list):
            missing={tuple(x):"1970-01-01" for x in raw_missing}
        elif isinstance(raw_missing,dict):
            missing={tuple(k.split("|")):v for k,v in raw_missing.items()}
            missing={(k[0],int(k[1]),k[2]):v for k,v in missing.items()}
        else:raise SystemExit("Invalid missing-period cache")
    else:
        missing={}
    outside=[item for item in db if not isinstance(item,tuple) or len(item)!=3 or item[0] not in tickers]
    if outside:raise SystemExit("Cached DB contains records outside selected KRX universe; refusing to mix datasets")
    missing={item:date for item,date in missing.items() if len(item)==3 and item[0] in tickers}
    today=dt.date.today()
    history={}
    if args.history_file:
        history_path=Path(args.history_file)
        if not history_path.is_file():raise SystemExit("History file missing; refusing to recollect blindly")
        document=json.loads(history_path.read_text(encoding="utf-8"))
        if document.get("schema_version")!=1 or not isinstance(document.get("entries"),dict):
            raise SystemExit("Invalid history format")
        history=document["entries"]
    tasks=[]
    cached=0
    unavailable_cached=0
    for code in selected:
        for year in range(args.start_year,args.end_year+1):
            for report in REPORTS:
                if year==today.year and {"q1":3,"half":6,"q3":9,"annual":12}[report]>today.month:
                    continue
                item=(code,year,report)
                entry=history.get(f"{code}|{year}|{report}",{})
                if args.history_file and entry.get("status")=="imported":
                    cached+=1
                elif args.history_file and entry.get("status")=="unavailable" and (year<today.year or (today-dt.date.fromisoformat(entry["checked_at"])).days<args.missing_recheck_days):
                    unavailable_cached+=1
                elif item in db:cached+=1
                elif item in missing and (year<today.year or (today-dt.date.fromisoformat(missing[item])).days<args.missing_recheck_days):unavailable_cached+=1
                else:tasks.append(item)
    stats={"selected":selected,"batch_index":args.batch_index,"batch_size":args.batch_size,
           "eligible":len(tickers),"cached":cached,"unavailable_cached":unavailable_cached,"downloaded":0,"unavailable":0,"errors":0}
    batch_started=time.monotonic()
    completed=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map={pool.submit(request,key,mapping[code]["corp_code"],year,report):(code,year,report)
                    for code,year,report in tasks}
        for future in concurrent.futures.as_completed(future_map):
            code,year,report=future_map[future]
            try:
                status,rows=future.result()
                if status=="ok":
                    db[(code,year,report)]={"ticker":code,"corp_code":mapping[code]["corp_code"],
                        "year":year,"report":report,"fs_div":"CFS","classification":"pending",
                        "collected_at":dt.datetime.now(dt.timezone.utc).isoformat(),"rows":rows}
                    stats["downloaded"]+=1
                elif status=="unavailable":
                    stats["unavailable"]+=1
                    missing[(code,year,report)]=today.isoformat()
                else:
                    stats["errors"]+=1
                    print("DART_COLLECT_ERROR",status)
            except (requests.RequestException,ValueError,OSError) as exc:
                stats["errors"]+=1
                print("DART_COLLECT_ERROR",type(exc).__name__)
            completed+=1
            if completed%20==0 or completed==len(tasks):
                print("DART_PROGRESS="+json.dumps({"completed":completed,"total":len(tasks),"elapsed_seconds":round(time.monotonic()-batch_started,1)}),flush=True)
    stats["elapsed_seconds"]=round(time.monotonic()-batch_started,1)
    save(db)
    MISSING.write_text(json.dumps({"|".join(map(str,k)):v for k,v in sorted(missing.items())},ensure_ascii=False,sort_keys=True),encoding="utf-8")
    stats["stored"]=len(db)
    stats["compressed_bytes"]=DB.stat().st_size
    print("PUBLIC_DART_BATCH="+json.dumps({k:v for k,v in stats.items() if k != "selected"},ensure_ascii=False))
    if stats["errors"]:raise SystemExit("Incomplete batch; errors require review")
if __name__=="__main__":main()
