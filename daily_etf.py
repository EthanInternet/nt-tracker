#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_etf.py
国家队宽基ETF份额日频追踪（东方财富直连版）
· 不依赖 akshare，速度快、稳定性高
· 按列位置取值，无视列名变化
· 自动回填历史数据，自动推送企微
"""

import os
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# ==================== 基础配置 ====================
plt.rcParams["font.sans-serif"] = ["SimHei", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

CSV = Path("nt_etf_shares.csv")
TODAY = pd.Timestamp.today().normalize()
PNG = "nt_etf_daily.png"

# ETF 标的（代码: 名称）
NT_ETFS = {
    "510300": "沪深300ETF",
    "510330": "沪深300ETF(华夏)",
    "510050": "上证50ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
}

# 东方财富接口
API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.eastmoney.com/"
}

# 首次运行时回溯的天数（自然日，约3个月）
LOOKBACK_DAYS = 90

# ==================== 数据获取 ====================
def fetch_etf_data(code: str, name: str, days: int = 1) -> pd.DataFrame:
    """
    从东方财富抓取单只ETF数据
    关键：按列位置取值，不依赖列名
    """
    end_date = TODAY.strftime("%Y%m%d")
    start_date = (TODAY - pd.Timedelta(days=days)).strftime("%Y%m%d")

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
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
        data = resp.json()

        if data.get("success") != True:
            print(f"  ⚠️ {name}({code}) 接口返回失败")
            return pd.DataFrame()

        rows = data["result"]["data"]
        if not rows:
            print(f"  ⚠️ {name}({code}) 无数据")
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # ★★★ 核心逻辑：按列位置取值 ★★★
        # 东方财富标准返回顺序：
        # [0]序号 [1]FCODE [2]FNAME [3]ETFTYPE [4]REPORT_DATE [5]SCALE_TOTAL
        # 我们只认位置，不认名字
        if len(df.columns) < 6:
            print(f"  ❌ {name} 列数不足：{len(df.columns)}")
            return pd.DataFrame()

        date_col = df.iloc[:, 4]       # 第5列：日期
        share_col = df.iloc[:, 5]      # 第6列：份额

        out = pd.DataFrame()
        out["date"] = pd.to_datetime(date_col, errors="coerce")
        out["shares"] = pd.to_numeric(share_col, errors="coerce")
        out["code"] = code
        out["name"] = name

        out = out.dropna(subset=["date", "shares"])
        out = out[out["shares"] > 0]
        out = out.sort_values("date").reset_index(drop=True)

        print(f"  ✅ {name}：{len(out)} 行，最新 {out['date'].max():%Y-%m-%d}")
        return out[["date", "code", "name", "shares"]]

    except Exception as e:
        print(f"  ❌ {name}({code}) 异常：{e}")
        return pd.DataFrame()

def fetch_all_history() -> pd.DataFrame:
    """全量拉取所有ETF的历史数据"""
    frames = []
    for code, name in NT_ETFS.items():
        print(f"↓ {name}({code})")
        df = fetch_etf_data(code, name, days=LOOKBACK_DAYS)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

# ==================== 绘图 ====================
def draw_chart(df: pd.DataFrame) -> bool:
    """绘制折线图"""
    try:
        df["shares_yi"] = df["shares"] / 1e8

        fig, ax = plt.subplots(figsize=(12, 6))
        for code, g in df.groupby("code"):
            g = g.sort_values("date")
            ax.plot(g["date"], g["shares_yi"],
                    label=g["name"].iloc[0],
                    marker=".",
                    markersize=3,
                    linewidth=1.2)

        ax.legend(fontsize=9)
        ax.set_ylabel("份额（亿份）")
        ax.set_title(f"国家队ETF份额追踪 ({df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d})")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        plt.tight_layout()
        plt.savefig(PNG, dpi=90, bbox_inches="tight")
        plt.close(fig)
        print(f"✅ 图表已生成：{PNG}")
        return True
    except Exception as e:
        print(f"❌ 绘图失败：{e}")
        return False

# ==================== 推送 ====================
def push_to_wecom(df: pd.DataFrame, note: str = ""):
    """推送图文到企业微信"""
    try:
        from wecom_push import push_image, push_markdown
    except ImportError:
        print("❌ 缺少 wecom_push 模块")
        return

    if not draw_chart(df):
        push_markdown(os.environ["WECOM_WEBHOOK"],
                      f"## ❌ 绘图失败\n> {note}")
        return

    push_image(os.environ["WECOM_WEBHOOK"], PNG)

    latest = df.groupby("code").apply(lambda x: x.sort_values("date").iloc[-1])
    lines = [f"## 📊 ETF日报 {TODAY:%Y-%m-%d}"]
    if note:
        lines.append(f"> {note}")
    lines.append(f"> 数据区间：{df['date'].min():%m-%d} ~ {df['date'].max():%m-%d}")
    for _, r in latest.iterrows():
        lines.append(f"- **{r['name']}**：{r['shares']/1e8:.2f}亿份")
    push_markdown(os.environ["WECOM_WEBHOOK"], "\n".join(lines))
    print("✅ 推送完成")

# ==================== 主函数 ====================
def main():
    print(f"🚀 启动 ETF 追踪 | {TODAY:%Y-%m-%d %A}\n")

    webhook = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not webhook:
        print("💥 WECOM_WEBHOOK 未设置！")
        return

    # 读取历史
    if CSV.exists():
        old = pd.read_csv(CSV)
        old["date"] = pd.to_datetime(old["date"], errors="coerce")
        print(f"📂 历史数据：{len(old)} 行")
    else:
        old = pd.DataFrame()
        print("📂 无历史数据")

    # 判断是否需要全量回填
    need_full = False
    if old.empty:
        need_full = True
        print("📭 首次运行，执行全量回填...")
    else:
        gap = (TODAY - old["date"].max()).days
        if gap > 7:
            need_full = True
            print(f"📭 数据陈旧（{gap}天），执行全量回填...")

    if need_full:
        new = fetch_all_history()
        if new.empty:
            print("💥 全量拉取失败")
            if not old.empty:
                push_to_wecom(old, "接口异常·展示历史数据")
            return
    else:
        # 仅拉今日
        parts = []
        for code, name in NT_ETFS.items():
            d = fetch_etf_data(code, name, days=1)
            if not d.empty:
                parts.append(d)
        new = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    if new.empty and old.empty:
        print("💥 无任何数据")
        return

    # 合并并保存
    final = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "code"])
    final = final.sort_values(["code", "date"]).reset_index(drop=True)
    final.to_csv(CSV, index=False)
    print(f"💾 数据已保存：{len(final)} 行")

    # 推送
    push_to_wecom(final)

if __name__ == "__main__":
    main()
