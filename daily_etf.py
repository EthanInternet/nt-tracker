"""
daily_etf.py — 国家队宽基ETF份额日频追踪
数据源：东方财富直连接口（快、稳、不依赖列名）
功能：抓取 → 合并CSV → 画图 → 推送企业微信
"""
import os, traceback
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
plt.rcParams["font.sans-serif"] = ["SimHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False

CSV = Path("nt_etf_shares.csv")
TODAY = pd.Timestamp.today().normalize()
PNG = "nt_etf_daily.png"

NT_ETFS = {
    "510300": "沪深300ETF",
    "510330": "沪深300ETF(华夏)",
    "510050": "上证50ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
}

# 东方财富接口
API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}

# 回溯天数（用于首次运行时补历史）
LOOKBACK_DAYS = 90  # 约3个月

# ============ 数据获取 ============
def fetch_history(code: str, name: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """
    从东方财富拉取单只ETF的历史份额数据
    关键：按列位置取值，完全不依赖列名
    """
    end = TODAY.strftime("%Y%m%d")
    start = (TODAY - pd.Timedelta(days=days)).strftime("%Y%m%d")
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
        r = requests.get(API, params=params, headers=HEADERS, timeout=20)
        j = r.json()
        if j.get("success") != True:
            print(f"  ⚠️ {name}({code}) 接口返回失败")
            return pd.DataFrame()
        rows = j["result"]["data"]
        if not rows:
            print(f"  ⚠️ {name}({code}) 无数据")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # ★ 核心：打印列名方便调试，按位置取值不依赖列名
        cols = list(df.columns)
        print(f"  🔍 {name} 列数={len(cols)}，前几列={cols[:8]}")

        # 东方财富返回字段顺序通常为：
        # [0]序号 [1]FCODE [2]FNAME [3]ETFTYPE [4]REPORT_DATE [5]SCALE... [6]...
        # 我们用位置 4 = 日期，位置 5 或 6 = 份额（取第一个数值型大数列）
        if len(cols) < 6:
            print(f"  ❌ {name} 列数太少：{cols}")
            return pd.DataFrame()

        date_raw = df.iloc[:, 4]   # 第5列=日期
        # 份额：从第5列开始找第一个数值型大数列（排除代码/名称等字符串列）
        share_raw = None
        for ci in range(5, len(cols)):
            s = pd.to_numeric(df.iloc[:, ci], errors="coerce")
            if s.dropna().shape[0] > 0:
                share_raw = s
                print(f"  📌 {name} 份额列位置={ci}，列名={cols[ci]}")
                break
        if share_raw is None:
            print(f"  ❌ {name} 找不到数值型份额列")
            return pd.DataFrame()

        out = pd.DataFrame({
            "date": pd.to_datetime(date_raw, errors="coerce"),
            "shares": pd.to_numeric(share_raw, errors="coerce"),
            "code": code,
            "name": name,
        }).dropna()
        out = out[out["shares"] > 0]
        out = out.sort_values("date").reset_index(drop=True)
        print(f"  ✅ {name}：{len(out)} 行，{out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")
        return out[["date", "code", "name", "shares"]]

    except Exception as e:
        print(f"  ❌ {name}({code}) 异常：{e}")
        traceback.print_exc()
        return pd.DataFrame()

def fetch_all() -> pd.DataFrame:
    """拉取所有ETF的历史数据"""
    parts = []
    for code, name in NT_ETFS.items():
        print(f"↓ {name}({code})")
        df = fetch_history(code, name)
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)

# ============ 画图 ============
def draw_chart(out: pd.DataFrame) -> bool:
    """画折线图，成功返回True"""
    try:
        out["shares_yi"] = out["shares"] / 1e8
        fig, ax = plt.subplots(figsize=(12, 5))

        for code, g in out.groupby("code"):
            g = g.sort_values("date")
            name = g["name"].iloc[0]
            ax.plot(g["date"], g["shares_yi"], label=name, marker=".", markersize=3, linewidth=1.2)

        ax.legend(fontsize=9, loc="upper left")
        ax.set_ylabel("份额（亿份）")
        ax.set_title(f"国家队宽基ETF份额追踪  {out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")
        ax.grid(True, alpha=0.3)
        # 美化x轴日期
        fig.autofmt_xdate()
        plt.tight_layout()
        plt.savefig(PNG, dpi=90, bbox_inches="tight")
        plt.close(fig)
        print(f"✅ saved {PNG}")
        return True
    except Exception as e:
        print(f"❌ 画图失败：{e}")
        traceback.print_exc()
        return False

# ============ 推送 ============
def push_all(out: pd.DataFrame, wh: str, note: str = ""):
    """画图 + 推送（图+文字）"""
    ok = draw_chart(out)
    if not ok:
        push_markdown(wh, f"## ❌ 画图失败\n> {note}")
        return

    # 推送图片
    try:
        from wecom_push import push_image, push_markdown
        push_image(wh, PNG)
    except Exception as e:
        print(f"❌ 推送图片失败：{e}")

    # 推送文字摘要
    last = out.groupby("code").apply(lambda g: g.sort_values("date").iloc[-1])
    lines = [f"## 📊 ETF日报 {TODAY:%Y-%m-%d}"]
    if note:
        lines.append(f"> {note}")
    lines.append(f"> 推送时间: {datetime.now():%H:%M:%S}")
    lines.append(f"> 数据区间: {out['date'].min():%m-%d} ~ {out['date'].max():%m-%d}")
    for _, r in last.iterrows():
        shares_yi = r["shares"] / 1e8
        lines.append(f"- **{r['name']}**：{shares_yi:.2f}亿份")
    text = "\n".join(lines)
    try:
        from wecom_push import push_markdown
        push_markdown(wh, text)
    except:
        pass
    print("✅ 推送完成")

# ============ 主流程 ============
def main():
    # 1. 读 Webhook
    wh = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not wh:
        print("💥 WECOM_WEBHOOK 未注入！检查 GitHub Secret")
        return

    # 2. 读旧 CSV
    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    if not old.empty and "date" in old.columns:
        old["date"] = pd.to_datetime(old["date"], errors="coerce")
        old = old.dropna(subset=["date"])
    print(f"📂 旧CSV：{len(old)} 行")

    # 3. 判断是否需要补历史
    # 如果CSV太旧或为空，就全量拉一次
    need_backfill = False
    if old.empty:
        need_backfill = True
        print("📭 CSV为空，执行全量回填...")
    else:
        latest = old["date"].max()
        days_gap = (TODAY - latest).days
        if days_gap > 7:
            need_backfill = True
            print(f"📭 CSV最新数据距今 {days_gap} 天，执行全量回填...")
        else:
            print(f"📅 CSV最新数据：{latest:%Y-%m-%d}（{days_gap}天前），仅追加今日")

    if need_backfill:
        new = fetch_all()
        if new.empty:
            print("💥 全量拉取失败，尝试用旧数据发图")
            if not old.empty:
                push_all(old.copy(), wh, "接口异常·展示最近可用数据")
            else:
                # 尝试直接推文字
                try:
                    from wecom_push import push_markdown
                    push_markdown(wh, "## 💥 ETF数据接口异常\n> 所有数据源均不可用，请检查")
                except:
                    pass
            return
        # 合并去重
        out = pd.concat([old, new], ignore_index=True).drop_duplicates(["date", "code"])
        out = out.sort_values(["code", "date"]).reset_index(drop=True)
        out.to_csv(CSV, index=False)
        print(f"💾 合并完成：{len(out)} 行")
        push_all(out, wh, "")
    else:
        # 只拉今天
        today_parts = []
        for code, name in NT_ETFS.items():
            today_data = fetch_history(code, name, days=1)
            if not today_data.empty:
                today_parts.append(today_data)
        if today_parts:
            today_df = pd.concat(today_parts, ignore_index=True)
            out = pd.concat([old, today_df], ignore_index=True).drop_duplicates(["date", "code"])
            out.to_csv(CSV, index=False)
            push_all(out, wh, "")
        else:
            print("⚠️ 今日无新数据，用历史发图")
            push_all(old.copy(), wh, "非交易日/接口异常·展示最近数据")

if __name__ == "__main__":
    print(f"🚀 启动 ETF 追踪 | 今天：{TODAY:%Y-%m-%d %A}\n")
    main()
    print("\n🏁 完成")
