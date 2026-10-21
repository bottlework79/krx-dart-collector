"""Read-only DART listed-company scope probe; never prints credentials."""
import argparse
import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET
import requests

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--batch-index",type=int,default=0)
    parser.add_argument("--batch-size",type=int,default=2)
    args=parser.parse_args()
    if args.batch_index<0 or not 1<=args.batch_size<=25:
        raise SystemExit("Invalid batch settings")
    key=os.environ.get("DART_API_KEY")
    if not key:raise SystemExit("Missing DART_API_KEY secret")
    response=requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                          params={"crtfc_key":key},timeout=90)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        with archive.open("CORPCODE.xml") as handle:
            root=ET.parse(handle).getroot()
    tickers=sorted({(item.findtext("stock_code") or "").strip()
                    for item in root.findall("list")
                    if len((item.findtext("stock_code") or "").strip())==6
                    and (item.findtext("stock_code") or "").strip().isdigit()})
    start=args.batch_index*args.batch_size
    selected=tickers[start:start+args.batch_size]
    if not selected:raise SystemExit("No tickers in selected batch")
    print("PUBLIC_DART_SCOPE="+json.dumps({"listed_tickers":len(tickers),
          "batch_index":args.batch_index,"batch_size":args.batch_size,
          "selected":selected}))
if __name__=="__main__":main()
