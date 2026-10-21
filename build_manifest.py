"""Produce a checksummed, non-sensitive manifest for a collector database."""
import argparse
import gzip
import hashlib
import json
import pickle
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="data/financial_statements.pkl.gz")
    p.add_argument("--universe",default="data/krx_universe.json")
    p.add_argument("--output",default="data/financial_manifest.json")
    a=p.parse_args()
    db=Path(a.db)
    universe=json.loads(Path(a.universe).read_text(encoding="utf-8"))
    if len(universe)!=len(set(universe)) or not universe:
        raise SystemExit("Invalid KRX universe")
    with gzip.open(db,"rb") as f:
        records=pickle.load(f)
    if not isinstance(records,dict):raise SystemExit("Invalid database")
    tickers=set()
    for key,payload in records.items():
        if not isinstance(key,tuple) or len(key)!=3 or not isinstance(payload,dict):
            raise SystemExit("Invalid statement record")
        ticker,year,report=key
        if ticker not in universe or payload.get("ticker")!=ticker or payload.get("year")!=year or payload.get("report")!=report:
            raise SystemExit("Statement outside approved universe")
        if payload.get("fs_div")!="CFS" or not isinstance(payload.get("rows"),list):
            raise SystemExit("Invalid CFS statement")
        tickers.add(ticker)
    result={"schema":"dart-cfs-pickle-v1","sha256":hashlib.sha256(db.read_bytes()).hexdigest(),
            "bytes":db.stat().st_size,"statements":len(records),"tickers":len(tickers),
            "universe_size":len(universe),"source":"public-dart-collector",
            "verified_fcf":False}
    target=Path(a.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("PUBLIC_DART_MANIFEST="+json.dumps(result))
if __name__=="__main__":main()
