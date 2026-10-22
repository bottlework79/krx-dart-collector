"""Merge a trusted freshly collected DART batch into a separate Private v2 DB.

Runs only in a trusted GitHub Actions checkout of the user's Private repository.
"""
import argparse
import gzip
import json
import os
import pickle
import tempfile
from pathlib import Path

def read(path):
    if not path.exists():return {}
    with gzip.open(path,"rb") as f: data=pickle.load(f)
    if not isinstance(data,dict):raise ValueError("Invalid financial DB")
    return data

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--batch",type=Path,required=True)
    p.add_argument("--private-db",type=Path,required=True)
    p.add_argument("--universe",type=Path,default=Path("data/krx_universe.json"))
    args=p.parse_args()
    allowed=set(json.loads(args.universe.read_text(encoding="utf-8")))
    incoming=read(args.batch)
    current=read(args.private_db)
    for key,value in incoming.items():
        if not isinstance(key,tuple) or len(key)!=3 or key[0] not in allowed or key[2] not in ("annual","q1","half","q3") or not isinstance(key[1],int):
            raise ValueError("Invalid key")
        if not isinstance(value,dict) or value.get("ticker")!=key[0] or value.get("year")!=key[1] or value.get("report")!=key[2] or value.get("fs_div")!="CFS" or not isinstance(value.get("rows"),list):
            raise ValueError("Invalid source record")
    for key in incoming.keys()&current.keys():
        if incoming[key].get("rows")!=current[key].get("rows"):
            raise ValueError("Conflicting financial record: "+str(key))
    current.update({key:value for key,value in incoming.items() if key not in current})
    args.private_db.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.private_db.parent,delete=False,suffix=".tmp") as f:tmp=Path(f.name)
    try:
        with gzip.open(tmp,"wb",compresslevel=6) as f:pickle.dump(current,f,protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp,args.private_db)
    finally:tmp.unlink(missing_ok=True)
    print("PRIVATE_V2_MERGE="+json.dumps({"incoming":len(incoming),"total":len(current),"private_path":str(args.private_db)}))
if __name__=="__main__":main()
