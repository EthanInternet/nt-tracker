"""
backfill_fast.py — 万能版
· 字段名自动识别，不依赖特定列名
· 跑完自动 commit（需 GITHUB_TOKEN）
· 打印真实列名方便排错
"""
import os, subprocess, sys
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
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"}

def fetch_one(code, name):
    params = {
        "reportName": "RPT_ETF_FUND_SCALE",
        "columns": "ALL",
        "filter": f"(FCODE=\"{code}\")",
        "pageNumber": "1", "pageSize": "500",
        "sortColumns": "REPORT_DATE", "sortTypes": "-1",
    }
    r = requests.get(API, params=params, headers=HEADERS, timeout=20)
    j = r.json()
    if not j.get("success"): 
        print(f"  ⚠️ {code} 接口 success=false"); return pd.DataFrame()
    rows = j["result"]["data"]
    if not rows: 
        print(f"  ⚠️ {code} 无数据"); return pd.DataFrame()

    df = pd.DataFrame(rows)
    print(f"  🔍 {code} 实际列名：{list(df.columns)}")

    # 找日期列
    date_col = None
    for c in df.columns:
        s = str(c).upper()
        if "DATE" in s or "日" in s: 
            date_col = c; break
    # 找份额列（挑数字最大、最像份额的那个）
    share_col = None
    candidates = []
    for c in df.columns:
        if any(k in str(c).upper() for k in ["SCALE","SHARE","FUND","AMOUNT","TOTAL","份额","规模"]):
            candidates.append(c)
    if candidates:
        # 选第一个数值列
        for c in candidates:
            if pd.api.types.is_numeric_dtype(df[c]):
                share_col = c; break
        if not share_col and candidates:
            share_col = candidates[0]

    if not date_col or not share_col:
        print(f"  ❌ {code} 找不到日期/份额列（日期={date_col}, 份额={share_col}）")
        return pd.DataFrame()

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce"),
        "shares": pd.to_numeric(df[share_col], errors="coerce"),
        "code": code, "name": name
    }).dropna()
    print(f"  ✅ {name}：{len(out)} 行，{out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")
    return out[["date","code","name","shares"]]

def commit_csv():
    """自动 commit 回仓库"""
    try:
        subprocess.run(["git","config","user.name","nt-bot"], check=True)
        subprocess.run(["git","config","user.email","nt-bot@github"], check=True)
        subprocess.run(["git","add",str(CSV)], check=True)
        subprocess.run(["git","commit","-m","backfill: update etf history"], check=True)
        # 需要 GITHUB_TOKEN 才能 push
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            remote = f"https://{token}@github.com/{os.environ.get('GITHUB_REPOSITORY','')}.git"
            subprocess.run(["git","push",remote,"HEAD"], check=True)
            print("  📤 已推回仓库")
        else:
            print("  ⚠️ 无 GITHUB_TOKEN，未 push（CI 里跑会自动有）")
    except Exception as e:
        print(f"  ⚠️ commit/push 异常：{e}")

def main():
    print("🚀 开始回填（万能字段版）\n")
    parts = []
    for code, name in NT_ETFS.items():
        print(f"↓ {name}({code})")
        df = fetch_one(code, name)
        if not df.empty: parts.append(df)

    if not parts:
        print("\n💥 全部失败，把上面的「实际列名」发给我"); return

    new = pd.concat(parts, ignore_index=True)

    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    if not old.empty and "date" in old.columns:
        old["date"] = pd.to_datetime(old["date"], errors="coerce")

    out = pd.concat([old, new]).drop_duplicates(["date","code"]).sort_values(["code","date"])
    out.to_csv(CSV, index=False)
    print(f"\n🎉 本地 CSV 完成：{len(out)} 行，{out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")

    commit_csv()

if __name__ == "__main__":
    main()
