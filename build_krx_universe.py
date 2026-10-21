"""Generate a public KRX ticker snapshot without reading the private price database.

Run separately; compare against the private 2,548-code snapshot before bulk collection.
"""
import datetime as dt
import json
from pathlib import Path

def main():
    from pykrx import stock
    today=dt.date.today()
    result=set()
    for market in ("KOSPI","KOSDAQ","KONEX"):
        result.update(stock.get_market_ticker_list(today.strftime("%Y%m%d"),market=market))
    tickers=sorted({str(code).zfill(6) for code in result if str(code).isdigit() and len(str(code))<=6})
    if len(tickers)<2000 or len(tickers)>4000:
        raise SystemExit("Unexpected KRX ticker count; refusing to publish snapshot")
    path=Path("data/krx_universe.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(tickers,ensure_ascii=False),encoding="utf-8")
    print("PUBLIC_KRX_SNAPSHOT="+json.dumps({"count":len(tickers),"as_of":today.isoformat(),"first":tickers[:5],"last":tickers[-5:]}))
    print("RECONCILIATION_REQUIRED: compare snapshot against private 2548-ticker universe before bulk collection")
if __name__=="__main__":main()
