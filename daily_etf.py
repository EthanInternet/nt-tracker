#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_etf.py — 国家队宽基ETF份额追踪
数据源（双接口兜底，免费）：
  1) 东方财富直连 RPT_ETF_FUND_SCALE（按列位置取值，不依赖列名）
  2) AkShare fund_etf_scale_sse（上交所官方份额公示）
非交易日/接口挂了 -> 用本地CSV旧数据画图并发企微，不静默
"""
import os
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, timedelta

plt.rcParams["font.sans-serif"] = ["SimHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False

CSV = Path("nt_etf_shares.csv")
TODAY = pd.Timestamp.today().normalize()
PNG = "nt_etf_daily.png"

# 6位代码 -> 名称（上交所宽基）
NT_ETFS = {
    "510300": "沪深300ETF",
    "510330": "沪深300ETF(华夏)",
    "510050": "上证50ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
}

LOOKBACK_DAYS = 90  # 首次回填3个月

EM_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EM_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"}


# ========== 接口1：东方财富直连（主用） ==========
def fetch_em(code6, name, days):
    end = TODAY.strftime("%Y%m%d")
    start = (TODAY - timedelta(days=days)).strftime("%Y%m%d")
    params = {
        "reportName": "RPT_ETF_FUND_SCALE",
        "columns": "ALL",
        "filter": f'(FCODE="{code6}")',
        "pageNumber": "1", "pageSize": "500",
        "sortColumns": "REPORT_DATE", "sortTypes": "-1",
    }
    try:
        r = requests.get(EM_API, params=params, headers=EM_HEADERS, timeout=20)
        j = r.json()
        if not j.get("success"):
            print(f"  ⚠️ {name} 东财接口失败")
            return pd.DataFrame()
        rows = j["result"]["data"]
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if len(df.columns) < 6:
            print(f"  ❌ {name} 列数异常：{len(df.columns)}")
            return pd.DataFrame()
        # 按位置：第4列=日期，第5列=份额(份)，第6列备选
        date_col = df.iloc[:, 4]
        share_col = df.iloc[:, 5]
        out = pd.DataFrame({
            "date": pd.to_datetime(date_col, errors="coerce"),
            "shares": pd.to_numeric(share_col, errors="coerce"),
            "code": code6, "name": name,
        }).dropna()
        out = out[out["shares"] > 0]
        if out.empty:
            return pd.DataFrame()
        print(f"  ✅(东财) {name}：{len(out)} 行，最新 {out['date'].max():%Y-%m-%d}")
        return out[["date", "code", "name", "shares"]]
    except Exception as e:
        print(f"  ❌ {name} 东财异常：{e}")
        return pd.DataFrame()


# ========== 接口2：AkShare 上交所兜底 ==========
def fetch_akshare(code6, name, days):
    try:
        import akshare as ak
        d = TODAY.strftime("%Y%m%d")
        df = ak.fund_etf_scale_sse(date=d)
        if df is None or df.empty:
            return pd.DataFrame()
        # 容错找列
        code_col = next((c for c in df.columns if "代码" in str(c) or "CODE" in str(c).upper()), None)
        share_col = next((c for c in df.columns if "份额" in str(c) or "SCALE" in str(c).upper()), None)
        if not code_col or not share_col:
            return pd.DataFrame()
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        r = df[df[code_col] == code6]
        if r.empty:
            return pd.DataFrame()
        s = pd.to_numeric(r.iloc[0][share_col], errors="coerce")
        if pd.isna(s):
            return pd.DataFrame()
        out = pd.DataFrame([{
            "date": TODAY, "code": code6, "name":、name, "shares": float(s)
        }])
        print(f"  ✅(akshare) {name}：{TODAY:%Y-%m-%d} {s:,.0f} 份")
        return out[["date", "code", "name", "shares"]]
    except Exception as e:
        print(f"  ❌ {name} akshare异常：{e}")
        return pd.DataFrame()


def fetch_one(code6, name):
    # 先东财直连拿历史，失败再用akshare补当日
    d = fetch_em(code6, name, LOOKBACK_DAYS)
    if not d.empty:
        return d
    d2 = fetch_akshare(code6, name, 1)
    if not d2.empty:
        return d2
    return pd.DataFrame()


def fetch_all():
    frames = []
    for code, name in NT_ETFS.items():
        print(f"↓ {name}({code})")
        df = fetch_one(code, name)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ========== 画图 ==========
def draw(out):
    out = out.copy()
    out["yi"] = out["shares"] / 1e8
    fig, ax = plt.subplots(figsize=(12, 5))
    for code, g in out.groupby("code"):
        g = g.sort_values("date")
        ax.plot(g["date"], g["yi"], label=g["name"].iloc[0], marker=".", ms=3)
    ax.legend(fontsize=9)
    ax.set_ylabel("份额（亿份）")
    ax.set_title(f"国家队ETF份额 {out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(PNG, dpi=72, bbox_inches="tight")
    plt.close(fig)
    print(f"✅ saved {PNG}")


# ========== 主流程 ==========
def main():
    print(f"🚀 {TODAY:%Y-%m-%d %A}")
    wh = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not wh:
        print("💥 WECOM_WEBHOOK 未注入"); return

    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    if not old.empty and "date" in old.columns:
        old["date"] = pd.to_datetime(old["date"], errors="coerce")

    need_full = old.empty or (TODAY - old["date"].max()).days > 7
    if need_full:
        print("📥 全量回填（东财+akshare兜底）")
        new = fetch_all()
        if new.empty:
            print("💥 双接口均无数据")
            if not old.empty:
                pass
            else:
                return
    else:
        print("📥 补今日")
        new = fetch_all()

    if new.empty and old.empty:
        print("💥 无任何数据可画")
        return

    final = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "code"])
    final = final.sort_values(["code", "date"]).reset_index(drop=True)
    final.to_csv(CSV, index=False)
    print(f"💾 CSV: {len(final)} 行")

    draw(final)

    from wecom_push import push_image, push_markdown
    push_image(wh, PNG)
    last = final.groupby("code").apply(lambda x: x.sort_values("date").iloc[-1])
    lines = [f"## ETF日报 {TODAY:%Y-%m-%d}"]
    if need_full and new.empty:
        lines.append("> 接口异常·展示最近可用数据")
    lines.append(f"> 区间 {final['date'].min():%m-%d}~{final['date'].max():%m-%d}")
    for _, r in last.iterrows():
        lines.append(f"- **{r['name']}**：{r['shares']/1e8:.2f}亿份")
    push_markdown(wh, "\n".join(lines))
    print("✅ 推送完成")


if __name__ == "__main__":
    main()
