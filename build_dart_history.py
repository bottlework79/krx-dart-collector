"""Build a public *metadata-only* ledger from verified private DB and DART missing reports.

Never mark a statement imported based only on public collection or an artifact.
Usage: python build_dart_history.py --private-db /path/to/private/financial_statements.pkl.gz
"""
import argparse
import datetime as dt
import gzip
import json
import pickle
from pathlib import Path

REPORTS={"annual","q1","half","q3"}

def load(path):
    with gzip.open(path,"rb") as f: result=pickle.load(f)
    if not isinstance(result,dict):raise ValueError("Invalid private financial DB")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--private-db",type=Path,required=True)
    p.add_argument("--missing",type=Path,default=Path("data/unavailable_periods.json"))
    p.add_argument("--universe",type=Path,default=Path("data/krx_universe.json"))
    p.add_argument("--output",type=Path,default=Path("data/dart_collection_history.json"))
    args=p.parse_args()
    allowed=set(json.loads(args.universe.read_text(encoding="utf-8")))
    db=load(args.private_db)
    entries={}
    for key,record in db.items():
        if not isinstance(key,tuple) or len(key)!=3 or not isinstance(record,dict):
            raise ValueError("Invalid statement")
        ticker,year,report=key
        if ticker not in allowed or not isinstance(year,int) or report not in REPORTS:
            raise ValueError("Invalid statement identity")
        if record.get("ticker")!=ticker or record.get("year")!=year or record.get("report")!=report or record.get("fs_div")!="CFS" or not isinstance(record.get("rows"),list):
            raise ValueError("Invalid statement contents")
        entries[f"{ticker}|{year}|{report}"]={"status":"imported"}
    # Preserve unavailable checks from earlier batches; imported records always win.
    if args.output.exists():
        previous=json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("schema_version")!=1 or not isinstance(previous.get("entries"),dict):
            raise ValueError("Invalid previous history")
        for key,value in previous["entries"].items():
            parts=key.split("|")
            if len(parts)!=3:continue
            ticker,year,report=parts
            if ticker in allowed and year.isdigit() and report in REPORTS and key not in entries and isinstance(value,dict) and value.get("status")=="unavailable":
                dt.date.fromisoformat(value["checked_at"])
                entries[key]={"status":"unavailable","checked_at":value["checked_at"]}
    if args.missing.exists():
        raw=json.loads(args.missing.read_text(encoding="utf-8"))
        if isinstance(raw,dict):
            for key,date in raw.items():
                parts=key.split("|")
                if len(parts)!=3:continue
                ticker,year,report=parts
                if ticker in allowed and year.isdigit() and report in REPORTS and key not in entries:
                    dt.date.fromisoformat(date)
                    entries[key]={"status":"unavailable","checked_at":date}
    result={"schema_version":1,"source":"verified_private_financial_db","entries":dict(sorted(entries.items()))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print("DART_HISTORY="+json.dumps({"imported":sum(v["status"]=="imported" for v in entries.values()),"unavailable":sum(v["status"]=="unavailable" for v in entries.values())}))
if __name__=="__main__":main()
