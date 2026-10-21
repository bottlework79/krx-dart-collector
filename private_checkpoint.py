"""Private, atomic, resumable checkpoint transport for the public DART runner.

Only a private repository receives the ZIP. Never publish raw DB as a public artifact.
"""
import argparse
import base64
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
import requests

OWNER="bottlework79"
REPO="krx-stock-data"
DEST="data/dart_collector_checkpoint.zip"
BASE=f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{DEST}"
FILES=("financial_statements.pkl.gz","unavailable_periods.json","financial_manifest.json")

def client():
    token=os.environ.get("PRIVATE_DATA_TOKEN")
    if not token:raise SystemExit("Missing PRIVATE_DATA_TOKEN (fine-grained token: private repo Contents read/write)")
    s=requests.Session()
    s.headers.update({"Authorization":"Bearer "+token,
                      "Accept":"application/vnd.github+json",
                      "X-GitHub-Api-Version":"2022-11-28"})
    return s

def get(s):
    r=s.get(BASE,timeout=60)
    if r.status_code==404:return None
    r.raise_for_status()
    return r.json()

def verify_archive(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=set(z.namelist())
        if not {"financial_statements.pkl.gz","unavailable_periods.json","financial_manifest.json"}<=names:
            raise ValueError("Checkpoint missing required files")
        manifest=json.loads(z.read("financial_manifest.json"))
        db=z.read("financial_statements.pkl.gz")
        if hashlib.sha256(db).hexdigest()!=manifest.get("sha256") or len(db)!=manifest.get("bytes"):
            raise ValueError("Checkpoint DB checksum mismatch")
        if manifest.get("schema")!="dart-cfs-pickle-v1":
            raise ValueError("Unexpected checkpoint schema")
        missing=json.loads(z.read("unavailable_periods.json"))
        if not isinstance(missing,list):raise ValueError("Invalid missing-period list")
        return {name:z.read(name) for name in FILES}

def download():
    with client() as s:
        item=get(s)
        if item is None:
            print("PRIVATE_CHECKPOINT=absent")
            return
        # GitHub Contents API returns base64 for small files; larger files require Git blob API.
        if item.get("encoding")!="base64" or not item.get("content"):
            raise RuntimeError("Checkpoint exceeds GitHub Contents API inline read limit")
        raw=base64.b64decode(item["content"])
        contents=verify_archive(raw)
        folder=Path("data")
        folder.mkdir(exist_ok=True)
        for name,data in contents.items():
            (folder/name).write_bytes(data)
        print("PRIVATE_CHECKPOINT="+json.dumps({"restored":True,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}))

def upload():
    folder=Path("data")
    contents={name:(folder/name).read_bytes() for name in FILES}
    manifest=json.loads(contents["financial_manifest.json"])
    if hashlib.sha256(contents["financial_statements.pkl.gz"]).hexdigest()!=manifest.get("sha256"):
        raise RuntimeError("Local manifest checksum mismatch")
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in FILES:z.writestr(name,contents[name])
    raw=stream.getvalue()
    verify_archive(raw)
    if len(raw)>90*1024*1024:
        raise RuntimeError("Checkpoint approaching GitHub Contents API 100MB limit")
    with client() as s:
        previous=get(s)
        body={"message":"Checkpoint DART public collector data (no analytics code)",
              "content":base64.b64encode(raw).decode("ascii")}
        if previous is not None:body["sha"]=previous["sha"]
        r=s.put(BASE,json=body,timeout=120)
        if r.status_code in (409,422):
            raise RuntimeError("Private checkpoint conflict; refusing to overwrite concurrent changes")
        r.raise_for_status()
    print("PRIVATE_CHECKPOINT="+json.dumps({"saved":True,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"statements":manifest["statements"]}))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["download","upload"])
    args=p.parse_args()
    if args.action=="download":download()
    else:upload()
