"""Validate an existing DART pickle DB before reusing it. Trusted project artifacts only."""
import argparse
import gzip
import hashlib
import json
import pickle
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="data/financial_statements.pkl.gz")
    p.add_argument("--universe",default="data/financial_universe.json")
    args=p.parse_args()
    path=Path(args.db)
    if not path.is_file():raise SystemExit("Financial DB missing")
    allowed=set(json.loads(Path(args.universe).read_text(encoding="utf-8")))
    with gzip.open(path,"rb") as f:db=pickle.load(f)
    if not isinstance(db,dict):raise SystemExit("Invalid DB root")
    tickers=set()
    for key,record in db.items():
        if not isinstance(key,tuple) or len(key)!=3 or not isinstance(record,dict):
            raise SystemExit("Invalid DB entry")
        ticker,year,report=key
        if ticker not in allowed or ticker!=record.get("ticker") or year!=record.get("year") or report!=record.get("report"):
            raise SystemExit("DB universe or record identity mismatch")
        if record.get("fs_div")!="CFS" or not isinstance(record.get("rows"),list):
            raise SystemExit("Invalid CFS record")
        tickers.add(ticker)
    print("PUBLIC_DART_DB_VALID="+json.dumps({"statements":len(db),"tickers":len(tickers),
         "bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}))
if __name__=="__main__":main()
