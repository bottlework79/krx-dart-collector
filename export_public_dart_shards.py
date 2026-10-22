"""Export public DART source records to deterministic, bounded Git-friendly shards.

This only writes public CFS source records; it never exports private analytics.
Run after restoring a trusted collector checkpoint.
"""
import argparse
import gzip
import json
import pickle
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="data/financial_statements.pkl.gz")
    p.add_argument("--universe",default="data/krx_universe.json")
    p.add_argument("--output",default="data/public_dart")
    p.add_argument("--group-size",type=int,default=100)
    args=p.parse_args()
    if not 1<=args.group_size<=100:raise SystemExit("Invalid group size")
    allowed=sorted(set(json.loads(Path(args.universe).read_text(encoding="utf-8"))))
    with gzip.open(args.db,"rb") as f: db=pickle.load(f)
    if not isinstance(db,dict):raise SystemExit("Invalid DB")
    positions={ticker:i//args.group_size for i,ticker in enumerate(allowed)}
    groups={}
    for key,record in db.items():
        if not isinstance(key,tuple) or len(key)!=3 or key[0] not in positions:
            raise SystemExit("Invalid/outside-universe record")
        if not isinstance(record,dict) or record.get("ticker")!=key[0] or record.get("fs_div")!="CFS":
            raise SystemExit("Invalid source record")
        groups.setdefault(positions[key[0]],{})[key]=record
    dest=Path(args.output)
    dest.mkdir(parents=True,exist_ok=True)
    for index,items in sorted(groups.items()):
        path=dest/f"dart_{index:03d}.pkl.gz"
        with gzip.open(path,"wb",compresslevel=6) as f:
            pickle.dump(dict(sorted(items.items())),f,protocol=pickle.HIGHEST_PROTOCOL)
        with gzip.open(path,"rb") as f: check=pickle.load(f)
        if check!=dict(sorted(items.items())):raise SystemExit("Shard validation failed")
        print("PUBLIC_DART_SHARD="+json.dumps({"file":str(path),"records":len(items),"bytes":path.stat().st_size}))
    print("PUBLIC_DART_EXPORT="+json.dumps({"shards":len(groups),"records":len(db)}))
if __name__=="__main__":main()
