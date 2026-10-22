"""Split trusted DART checkpoint for cache, and reconstruct it for existing workflows."""
import argparse
import gzip
import json
import pickle
from pathlib import Path

def read(path):
    with gzip.open(path,"rb") as f: return pickle.load(f)

def write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,"wb",compresslevel=6) as f: pickle.dump(data,f,protocol=pickle.HIGHEST_PROTOCOL)

def split(db_path, shard_dir, universe_path):
    db=read(db_path)
    if not isinstance(db,dict): raise ValueError("Invalid DB")
    universe=sorted(set(json.loads(universe_path.read_text(encoding="utf-8"))))
    positions={code:i//100 for i,code in enumerate(universe)}
    groups={}
    for key,value in db.items():
        if not isinstance(key,tuple) or len(key)!=3 or key[0] not in positions:
            raise ValueError("Invalid ticker/key")
        groups.setdefault(positions[key[0]],{})[key]=value
    shard_dir.mkdir(parents=True,exist_ok=True)
    expected=set()
    for group,items in groups.items():
        path=shard_dir/f"dart_{group:03d}.pkl.gz"
        write(path,items)
        expected.add(path.name)
    for old in shard_dir.glob("dart_*.pkl.gz"):
        if old.name not in expected:old.unlink()
    check=merge(shard_dir)
    if check!=db:raise ValueError("Split round-trip mismatch")
    print("DART_SHARDS="+json.dumps({"files":len(groups),"records":len(db)}))

def merge(shard_dir):
    merged={}
    for path in sorted(shard_dir.glob("dart_*.pkl.gz")):
        shard=read(path)
        if not isinstance(shard,dict):raise ValueError("Invalid shard")
        if set(merged).intersection(shard):raise ValueError("Duplicate shard keys")
        merged.update(shard)
    return merged

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["split","restore"])
    p.add_argument("--db",type=Path,default=Path("data/financial_statements.pkl.gz"))
    p.add_argument("--shards",type=Path,default=Path("data/dart_shards"))
    p.add_argument("--universe",type=Path,default=Path("data/krx_universe.json"))
    args=p.parse_args()
    if args.action=="split":
        if not args.db.exists():raise SystemExit("Missing DB")
        split(args.db,args.shards,args.universe)
    else:
        if args.db.exists():
            print("DART_RESTORE=legacy_db_present")
            return
        if not list(args.shards.glob("dart_*.pkl.gz")):
            print("DART_RESTORE=no_checkpoint")
            return
        db=merge(args.shards)
        write(args.db,db)
        print("DART_RESTORE="+json.dumps({"records":len(db)}))
if __name__=="__main__":main()
