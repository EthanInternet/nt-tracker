#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import tushare as ts
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

plt.rcParams["font.sans-serif"] = ["SimHei", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

CSV = Path("nt_etf_shares.csv")
TODAY = pd.Timestamp.today().normalize()
PNG = "nt_etf_daily.png"

# ETF 代码（Tushare 格式：6位+市场后缀）
NT_ETFS = {
    "510300.SH": "沪深300ETF",
    "510330.SH": "沪深300ETF(华夏)",
    "510050.SH": "上证50ETF",
    "510500.SH": "中证500ETF",
    "512100.SH": "中证1000ETF",
}

LOOKBACK_DAYS = 90  # 首次回填3个月

# ---------- 数据层 ----------
def init_ts():
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        print("💥 TUSHARE_TOKEN 未注入")
        return None
    ts.set_token(token)
    return ts.pro_api()

def fetch_one(pro, ts_code, name, days):
    start = (TODAY - pd.Timedelta(days=days)).strftime("%Y%m%d")
    end = TODAY.strftime("%Y%m%d")
    try:
        # 优先用 etf_share_size（字段干净）
        df = pro.etf_share_size(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            # 降级用 fund_share（需转万份）
            df = pro.fund_share(ts_code=ts_code, start_date=start, end_date=end)
            if df is None or df.empty:
                print(f"  ⚠️ {name} 无数据")
                return pd.DataFrame()
            df = df.rename(columns={"fd_share": "total_share"})
            df["total_share"] = pd.to_numeric(df["total_share"], errors="coerce")  # 万份
        df = df.rename(columns={"trade_date": "date", "total_share": "share_wan"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["share_wan"] = pd.to_numeric(df["share_wan"], errors="coerce")
        df = df.dropna(subset=["date", "share_wan"])
        out = pd.DataFrame({
            "date": df["date"],
            "code": ts_code[:6],
            "name": name,
            "shares": df["share_wan"] * 1e4,  # 万份 -> 份
        })
        print(f"  ✅ {name}：{len(out)} 行，{out['date'].max():%Y-%m-%d}")
        return out[["date", "code", "name", "shares"]]
    except Exception as e:
        print(f"  ❌ {name} 异常：{e}")
        return pd.DataFrame()

def fetch_all(pro, days):
    frames = []
    for code, name in NT_ETFS.items():
        print(f"↓ {name}({code})")
        d = fetch_one(pro, code,名=name, days=days)
        if not d.empty:
            frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ---------- 画图 ----------
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
    plt.savefig(PNG, dpi=90, bbox_in="./")
    plt.close(fig)
    print(f"✅ saved {PNG}")

# ---------- 主流程 ----------
def main():
    print(f"🚀 {TODAY:%Y-%m-%d %A}")
    pro = init_ts()
    if pro is None:
        return

    wh = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not wh:
        print("💥 WECOM_WEBHOOK 未注入")
        return

    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    if not old.empty and "date" in old.columns:
        old["date"] = pd.to_datetime(old["date"], errors="coerce")

    need_full = old.empty or (TODAY - old["date"].max()).days > 7
    if need_full:
        print("📥 全量回填...")
        new = fetch_all(pro, LOOKBACK_DAYS)
        if new.empty:
            print("💥 拉取失败")
            if not old.empty:
                pass
            else:
                return
    else:
        print("📥 仅补今日...")
        new = fetch_all(pro, 1)

    final = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "code"])
    final = final.sort_values(["code", "date"]).reset_index(drop=True)
    final.to_csv(CSV, index=False)
    print(f"💾 CSV: {len(final)} 行")

    draw(final)

    # 推送
    from wecom_push import push_image, push_markdown
    push_image(wh, PNG)
    last = final.groupby("code").apply(lambda x: x.sort_values("date").iloc[-1])
    lines = [f"## ETF日报 {TODAY:%Y-%m-%d}", f"> 区间 {final['date'].min():%m-%d}~{final['date'].max():%m-%d}"]
    for _, r in last.iterrows():
        lines.append(f"- **{r['name']}**：{r['shares']/1e8:.2f}亿份")
    push_markdown(wh, "\n".join(lines))
    print("✅ 推送完成")

if __name__ == "__main__":
    main()
