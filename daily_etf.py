import akshare as ak
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import os
from datetime import datetime, timedelta

# 假设 config.py 在同一目录，或者你直接在这里定义
NT_ETFS = {
    "510300": "沪深300ETF",
    "510330": "中证500ETF",
    "510050": "上证50ETF",
    "510500": "中证500ETF(南方)",
    "512100": "中证1000ETF",
}

CSV = Path("nt_etf_shares.csv")
TODAY = pd.Timestamp.today().normalize()
PNG = "nt_etf_daily.png"

plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

def fetch(code):
    """带重试和异常捕获的抓取函数"""
    try:
        # 有时候日期格式不对，尝试用字符串
        date_str = TODAY.strftime("%Y%m%d")
        
        # 尝试获取上交所数据
        df = ak.fund_etf_scale_sse(date=date_str)
        
        if df is None or df.empty:
            print(f"⚠️  {code}: 今天（{date_str}）上交所返回空数据，可能是非交易日或接口异常")
            return None
            
        r = df[df["基金代码"] == code]
        if r.empty:
            print(f"❌ {code}: 在上交所数据中没找到该代码")
            return None
            
        return {
            "date": TODAY,
            "code": code,
            "name": NT_ETFS.get(code, code),
            "shares": float(r.iloc[0]["基金份额"]),
        }
    except Exception as e:
        print(f"❌ fetch err {code} {e}")
        return None

def main():
    # 1. 读取历史数据
    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    # 确保历史数据的日期是日期格式
    if not old.empty and 'date' in old.columns:
        old['date'] = pd.to_datetime(old['date'])

    # 2. 尝试抓取今天数据
    rows = [fetch(c) for c in NT_ETFS]
    new = pd.DataFrame([r for r in rows if r])

    # 3. 合并逻辑
    if new.empty:
        print("🚨 今天没有抓到任何新数据！检查是否为非交易日或网络问题。")
        # 如果没有新数据，但为了能继续发图（比如发昨天的），我们用历史数据画
        if old.empty:
            print("❌ 也没有历史数据，程序退出。")
            return
        out = old.copy()
    else:
        out = pd.concat([old, new]).drop_duplicates(["date", "code"])
        out.to_csv(CSV, index=False)

    # 4. 画图逻辑（这里加个判断防止 out 为空）
    if out.empty:
        print("❌ 最终数据为空，无法画图。")
        return

    out["shares_yi"] = out["shares"] / 1e8
    # 只画有数据的
    out = out.dropna(subset=["shares_yi"])

    fig, ax = plt.subplots(figsize=(12, 5))
    for code, group in out.groupby("code"):
        ax.plot(group["date"], group["shares_yi"], label=group["name"].iloc[0], marker='o')
    ax.legend()
    ax.set_title(f"国家队宽基ETF份额跟踪 {out['date'].min():%Y-%m-%d} ~ {out['date'].max():%Y-%m-%d}")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(PNG, dpi=120, bbox_inches="tight")
    print(f"✅ saved {PNG}")

    # 5. （可选）如果有 wecom_push.py，可以在这里调用
    # 为了演示，我们先不强制调用，你可以手动加回去

if __name__ == "__main__":
    main()
