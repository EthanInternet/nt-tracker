"""
backfill_fast.py
用东方财富接口，30 秒跑完 3 个月历史
"""
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

CSV = Path("nt_etf_shares.csv")

NT_ETFS = {
    "510300": "沪深300ETF",
    "510330": "沪深300ETF(华夏)",
    "510050": "上证50ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
}

API = "https://datacenter-web.eastmoney.com/api/data/v1/get"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.eastmoney.com/"
}

def fetch_one(code: str, name: str) -> pd.DataFrame:
    params = {
        "reportName": "RPT_ETF_FUND_SCALE",
        "columns": "ALL",
        "filter": f"(FCODE=\"{code}\")",
        "pageNumber": "1",
        "pageSize": "500",
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
    }
    try:
        r = requests.get(API, params=params, headers=HEADERS, timeout=15)
        j = r.json()
        if j.get("success") != True:
            print(f"  ⚠️ {code} 接口失败")
            return pd.DataFrame()
        rows = j["result"]["data"]
        if not rows:
            print(f"  ⚠️ {code} 无数据")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        date_col = next(c for c in df.columns if "DATE" in c or "日期" in c)
        share_col = next(c for c in df.columns if "SCALE" in c or "份额" in c)

        out = pd.DataFrame()
        out["date"] = pd.to_datetime(df[date_col])
        out["shares"] = pd.to_numeric(df[share_col], errors="coerce")
        out = out.dropna()
        out["code"] = code
        out["name"] = name
        print(f"  ✅ {name}：{len(out)} 行")
        return out[["date", "code", "name", "shares"]]
    except Exception as e:
        print(f"  ❌ {code} 异常：{e}")
        return pd.DataFrame()

def main():
    print("🚀 高速回填（东方财富接口）\n")
    parts = []

    for code, name in NT_ETFS.items():
        print(f"↓ {name}({code})")
        df = fetch_one(code, name)
        if not df.empty:
            parts.append(df)

    if not parts:
        print("💥 全部失败")
        return

    new = pd.concat(parts, ignore_index=True)

    if CSV.exists():
        old = pd.read_csv(CSV)
        old["date"] = pd.to_datetime(old["date"], errors="coerce")
    else:
        old = pd.DataFrame(columns=["date","code","name","shares"])

    out = pd.concat([old, new]).drop_duplicates(["date","code"])
    out = out.sort_values(["code","date"])
    out.to_csv(CSV, index=False)

    print(f"\n🎉 完成！共 {len(out)} 行")
    print(f"   日期：{out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")

if __name__ == "__main__":
    main()
