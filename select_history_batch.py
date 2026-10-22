"""Select next DART batch from PUBLIC imported-history metadata, not public raw DB."""
import argparse
import datetime as dt
import json
from pathlib import Path

REPORTS=("annual","q1","half","q3")
MONTH={"annual":12,"q1":3,"half":6,"q3":9}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--batch-size",type=int,default=2)
    p.add_argument("--start-year",type=int,default=2021)
    p.add_argument("--end-year",type=int,default=dt.date.today().year)
    p.add_argument("--history",type=Path,default=Path("data/dart_collection_history.json"))
    args=p.parse_args()
    if not 1<=args.batch_size<=25:raise SystemExit("Invalid batch size")
    today=dt.date.today()
    universe=sorted(set(json.loads(Path("data/krx_universe.json").read_text(encoding="utf-8"))))
    history=json.loads(args.history.read_text(encoding="utf-8")) if args.history.exists() else {"schema_version":1,"entries":{}}
    entries=history["entries"]
    for i in range(0,len(universe),args.batch_size):
        selected=universe[i:i+args.batch_size]
        pending=0
        for ticker in selected:
            for year in range(args.start_year,args.end_year+1):
                for report in REPORTS:
                    if year==today.year and MONTH[report]>today.month:continue
                    entry=entries.get(f"{ticker}|{year}|{report}",{})
                    if entry.get("status")=="imported":continue
                    if entry.get("status")=="unavailable":
                        checked=dt.date.fromisoformat(entry["checked_at"])
                        if year<today.year or (today-checked).days<7:continue
                    pending+=1
        if pending:
            print("AUTO_DART_BATCH="+json.dumps({"batch_index":i//args.batch_size,"batch_size":args.batch_size,"pending":pending,"selected":selected}))
            return
    raise SystemExit("No incomplete batches")
if __name__=="__main__":main()
