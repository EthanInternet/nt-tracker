import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
import akshare as ak
from config import NT_ETFS
from wecom_push import push_image, push_markdown

plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Zen Hei", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

CSV = Path("nt_etf_shares.csv")
TODAY = pd.Timestamp.today().normalize()

def fetch(code):
    try:
        df = ak.fund_etf_scale_sse(date=TODAY.strftime("%Y%m%d"))
        r = df[df["基金代码"] == code]
        if r.empty:
            return None
        return {"date": TODAY, "code": code, "name": NT_ETFS[code],
                "shares": float(r.iloc[0]["基金份额"])}
    except Exception as e:
        print("fetch err", code, e)
        return None

def main():
    old = pd.read_csv(CSV) if CSV.exists() else pd.DataFrame()
    rows = [fetch(c) for c in NT_ETFS]
    new = pd.DataFrame([x for x in rows if x])
    out = pd.concat([old, new]).drop_duplicates(["date", "code"])
    out.to_csv(CSV, index=False)

    out["shares_yi"] = out["shares"] / 1e8
    out["delta"] = out.groupby("code")["shares_yi"].diff()

    fig, ax = plt.subplots(figsize=(12, 5))
    for _, g in out.groupby("code"):
        ax.plot(g["date"], g["shares_yi"], label=g["name"].iloc[0])
    ax.set_ylabel("份额(亿份)")
    ax.legend()
    ax.set_title("国家队宽基ETF份额日频跟踪")
    plt.tight_layout()
    fig.savefig("nt_etf_daily.png", dpi=90)
    plt.close(fig)

    # 推送
    wh = os.environ["WECOM_WEBHOOK"]
    push_image(wh, "nt_etf_daily.png")

    last = out.dropna(subset=["delta"]).groupby("code").tail(1)
    lines = ["## 国家队ETF份额日报", f"> 日期：{TODAY:%Y-%m-%d}"]
    for _, row in last.iterrows():
        lines.append(f"- {row['name']}：{row['shares_yi']:.2f}亿份，日变动 {row['delta']:+.2f}亿")
    push_markdown(wh, "\n".join(lines))

if __name__ == "__main__":
    main()
