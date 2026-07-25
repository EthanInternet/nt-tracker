"""
回填历史 ETF 份额到 nt_etf_shares.csv
用法：python backfill.py
默认回溯：最近 90 个自然日（约 3 个月 / ~60 个交易日）
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

CSV = Path("nt_etf_shares.csv")

# ETF 代码 -> 名称（和 daily_etf.py 保持一致）
NT_ETFS = {
    "510300": "沪深300ETF",
    "510330": "沪深300ETF(华夏)",
    "510050": "上证50ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
}

# ★ 已按要求改为 90 天（约 3 个月）
LOOKBACK_DAYS = 90

def fetch_history(code: str, name: str) -> pd.DataFrame:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    print(f"  ↳ 请求区间：{start} ~ {end}")

    try:
        df = ak.fund_etf_fund_info_em(symbol=code, start_date=start, end_date=end)
    except Exception as e:
        print(f"  ⚠️ {code} 接口异常：{e}")
        return pd.DataFrame()

    if df is None or df.empty:
        print(f"  ⚠️ {code}：返回为空")
        return pd.DataFrame()

    # 兼容不同版本的列名
    col_map = {}
    for c in df.columns:
        s = str(c).strip()
        if "日期" in s or s.lower() == "date":
            col_map[c] = "date"
        if "份额" in s:
            col_map[c] = "shares"
    if len(col_map) < 2:
        print(f"  ⚠️ {code} 找不到份额列，实际列={list(df.columns)}")
        return pd.DataFrame()

    out = df.rename(columns=col_map)[["date", "shares"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["shares"] = pd.to_numeric(out["shares"], errors="coerce") * 1e8  # 亿份 -> 份
    out = out.dropna(subset=["shares"])
    out["code"] = code
    out["name"] = name
    return out[["date", "code", "name", "shares"]]

def main():
    print(f"🔄 开始回填，回溯 {LOOKBACK_DAYS} 天（约 3 个月）\n")
    parts = []

    for code, name in NT_ETFS.items():
        print(f"↓ 拉取 {name}({code}) ...")
        df = fetch_history(code, name)
        if df.empty:
            print(f"  ❌ 跳过\n")
            continue
        print(f"  ✅ 拿到 {len(df)} 行，"
              f"{df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d}\n")
        parts.append(df)

    if not parts:
        print("💥 全部失败，检查 akshare 接口或网络")
        return

    new = pd.concat(parts, ignore_index=True)

    # 合并到已有 CSV（去重）
    if CSV.exists():
        old = pd.read_csv(CSV)
        old["date"] = pd.to_datetime(old["date"], errors="coerce")
    else:
        old = pd.DataFrame(columns=["date", "code", "name", "shares"])

    out = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "code"])
    out = out.sort_values(["code", "date"])
    out.to_csv(CSV, index=False)

    print(f"\n🎉 回填完成！")
    print(f"   总条数：{len(out)}")
    print(f"   日期范围：{out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")
    print(f"   文件：{CSV}")

if __name__ == "__main__":
    main()
