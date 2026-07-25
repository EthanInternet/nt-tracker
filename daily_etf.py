import os, traceback
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import akshare as ak
from datetime import datetime
from wecom_push import push_image, push_markdown

plt.rcParams["font.sans-serif"] = ["SimHei","Noto Sans CJK SC","WenQuanYi Zen Hei"]
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

# ---------- 关键：鲁棒地找“代码列”和“份额列” ----------
def find_cols(df: pd.DataFrame):
    """从混乱的列名里猜出 代码列 和 份额列"""
    cols = list(df.columns)
    code_col = share_col = None
    for c in cols:
        s = str(c).strip().lower().replace(" ","")
        if any(k in s for k in ["基金代码","fundcode","code","证券代码"]):
            code_col = c
        if any(k in s for k in ["基金份额","份额","基金规模","scale","share"]):
            share_col = c
    return code_col, share_col

def fetch(code):
    try:
        df = ak.fund_etf_scale_sse(date=TODAY.strftime("%Y%m%d"))
        if df is None or df.empty:
            print(f"⚠️ {code}: 接口返回空")
            return None

        # 清掉可能的多级表头
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = ["_".join(str(x).strip() for x in c if str(x).strip())
                          for c in df.columns.values]

        code_col, share_col = find_cols(df)
        if not code_col or not share_col:
            print(f"❌ {code}: 找不到代码/份额列，实际列={list(df.columns)}")
            return None

        # 标准化代码格式（去前导0、转字符串）
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        r = df[df[code_col] == code]
        if r.empty:
            # 再试一次：不补零
            r = df[df[code_col].str.contains(code, na=False)]
        if r.empty:
            print(f"❌ {code}: 在返回结果中未匹配到")
            return None

        shares = pd.to_numeric(r.iloc[0][share_col], errors="coerce")
        if pd.isna(shares):
            print(f"❌ {code}: 份额非数值")
            return None

        return {"date": TODAY, "code": code,
                "name": NT_ETFS[code], "shares": float(shares)}
    except Exception as e:
        print(f"❌ fetch err {code}: {e}")
        return None

# ---------- 统一画图+推送 ----------
def draw_and_push(out, wh, note=""):
    if out is None or out.empty:
        push_markdown(wh, f"## ⚠️ {note}\n> 无可用数据，无法出图")
        return

    out["shares_yi"] = pd.to_numeric(out["shares"], errors="coerce") / 1e8
    out = out.dropna(subset=["shares_yi"])
    if out.empty:
        push_markdown(wh, f"## ❌ {note}\n> 数据无效")
        return

    fig, ax = plt.subplots(figsize=(10, 4))
    for _, g in out.groupby("code"):
        ax.plot(g["date"], g["shares_yi"], label=g["name"].iloc[0], marker=".")
    ax.legend(fontsize=8)
    ax.set_title(f"ETF份额 {out['date'].min():%m-%d} ~ {out['date'].max():%m-%d}")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(PNG, dpi=80)
    plt.close(fig)
    print(f"saved {PNG}")

    push_image(wh, PNG)

    last = out.groupby("code").tail(1)
    lines = [f"## ETF日报 {TODAY:%Y-%m-%d}"]
    if note: lines.append(f"> {note}")
    lines.append(f"> 推送时间: {datetime.now():%H:%M:%S}")
    for _, r in last.iterrows():
        lines.append(f"- {r['name']}: {r['shares_yi']:.2f}亿份")
    push_markdown(wh, "\n".join(lines))

# ---------- 主流程 ----------
def main():
    try:
        wh = os.environ["WECOM_WEBHOOK"]
    except KeyError:
        print("💥 WECOM_WEBHOOK 未注入，检查 Secret")
        return

    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    if not old.empty and "date" in old.columns:
        old["date"] = pd.to_datetime(old["date"], errors="coerce")

    rows = [fetch(c) for c in NT_ETFS]
    new = pd.DataFrame([r for r in rows if r])

    if new.empty:
        print("⚠️ 今日无新数据，用历史数据发图")
        draw_and_push(old.copy(), wh, "非交易日/接口异常·展示最近数据")
        return

    out = pd.concat([old, new]).drop_duplicates(["date","code"])
    out.to_csv(CSV, index=False)
    draw_and_push(out, wh, "")

if __name__ == "__main__":
    main()
