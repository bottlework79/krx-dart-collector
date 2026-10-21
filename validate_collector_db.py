"""Validate a collector database without publishing its raw contents."""
import argparse
import gzip
import hashlib
import json
import pickle
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",default="data/financial_statements.pkl.gz")
    p.add_argument("--universe",default="data/krx_universe.json")
    args=p.parse_args()
    db_path=Path(args.database)
    universe=json.loads(Path(args.universe).read_text(encoding="utf-8"))
    if not isinstance(universe,list) or len(universe)!=len(set(universe)):
        raise SystemExit("Invalid or duplicate universe")
    allowed=set(universe)
    with gzip.open(db_path,"rb") as f:
        records=pickle.load(f)
    if not isinstance(records,dict):
        raise SystemExit("Invalid database format")
    tickers=set()
    for key,payload in records.items():
        if not isinstance(key,tuple) or len(key)!=3 or not isinstance(payload,dict):
            raise SystemExit("Invalid record shape")
        code,year,report=key
        if code not in allowed or payload.get("ticker")!=code or payload.get("year")!=year or payload.get("report")!=report:
            raise SystemExit("Record key/payload mismatch or outside KRX universe")
        if payload.get("fs_div")!="CFS" or not isinstance(payload.get("rows"),list):
            raise SystemExit("Invalid consolidated statement payload")
        tickers.add(code)
    digest=hashlib.sha256(db_path.read_bytes()).hexdigest()
    print("PUBLIC_DART_VALIDATION="+json.dumps({
        "records":len(records),"tickers":len(tickers),"universe":len(allowed),
        "sha256":digest,"bytes":db_path.stat().st_size,
        "note":"Structural checks only; not financial statement or FCF verification."
    }))
if __name__=="__main__":main()
