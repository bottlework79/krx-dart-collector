"""Choose first incomplete 25-company KRX DART batch using saved coverage."""
import argparse
import datetime as dt
import gzip
import json
import pickle
from pathlib import Path

REPORTS=("annual","q1","half","q3")
MONTH={"annual":12,"q1":3,"half":6,"q3":9}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--batch-size",type=int,default=25)
    p.add_argument("--start-year",type=int,default=2021)
    p.add_argument("--end-year",type=int,default=dt.date.today().year)
    p.add_argument("--missing-recheck-days",type=int,default=7)
    args=p.parse_args()
    if not 1<=args.batch_size<=25:raise SystemExit("Invalid batch size")
    today=dt.date.today()
    tickers=sorted(set(json.loads(Path("data/krx_universe.json").read_text(encoding="utf-8"))))
    path=Path("data/financial_statements.pkl.gz")
    if path.exists():
        with gzip.open(path,"rb") as f:db=pickle.load(f)
    else:db={}
    mp=Path("data/unavailable_periods.json")
    raw=json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    if isinstance(raw,list):
        missing={(str(x[0]),int(x[1]),str(x[2])):"1970-01-01" for x in raw}
    elif isinstance(raw,dict):
        missing={(parts[0],int(parts[1]),parts[2]):v for k,v in raw.items() if len(parts:=k.split("|"))==3}
    else:raise SystemExit("Invalid missing cache")
    for i in range(0,len(tickers),args.batch_size):
        group=tickers[i:i+args.batch_size]
        pending=0
        for code in group:
            for year in range(args.start_year,args.end_year+1):
                for report in REPORTS:
                    if year==today.year and MONTH[report]>today.month:continue
                    item=(code,year,report)
                    if item in db:continue
                    cached=missing.get(item)
                    if cached:
                        age=(today-dt.date.fromisoformat(cached)).days
                        if year<today.year or age<args.missing_recheck_days:continue
                    pending+=1
        if pending:
            print("AUTO_DART_BATCH="+json.dumps({"batch_index":i//args.batch_size,"batch_size":args.batch_size,"pending":pending,"selected":group}))
            return
    raise SystemExit("No incomplete batches")
if __name__=="__main__":main()
