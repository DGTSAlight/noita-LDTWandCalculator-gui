# -*- coding: utf-8 -*-
"""把 sensitivity.py 的结果画成图（供讲解页使用）。

输出到 docs/charts/：
  sens_tornado.png  各系数 ±25% 对平均 S 的影响
  sens_zones.png    三个刷点各自的优势区间（代表法术）+ 每轮产出与耗时
  sens_rounds.png   「最小总轮数」与「最小总时间」两种目标的差距

用法：python scripts/analysis/plot_sensitivity.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "parsed", "sensitivity.json")
OUT = os.path.join(ROOT, "docs", "charts")

for name in ("Microsoft YaHei", "SimHei"):
    if name in {f.name for f in font_manager.fontManager.ttflist}:
        plt.rcParams["font.sans-serif"] = [name]
        break
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["axes.edgecolor"] = "#9aa0aa"
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["grid.color"] = "#e3e6ec"

INK = "#22262e"
DIM = "#6b7280"
DOWN = "#4a7fd4"     # 系数调小
UP = "#d4763a"       # 系数调大

GROUP_COLOR = {
    "地形": "#8c6bb1",
    "搜索动作": "#4a90a4",
    "密度": "#5aa469",
    "库存": "#d9a13b",
    "换世界": "#b5546a",
    "聚合": "#8a8f98",
}

ZONE_CN = {"holy": "圣山", "fungi": "繁茂", "hell": "地狱"}
ZONE_COLOR = {"holy": "#e0b252", "fungi": "#5aa469", "hell": "#b5546a"}

NAME_FIX = {"BLACK_HOLE": "黑洞"}


def load():
    return json.load(open(DATA, encoding="utf-8"))


def fig_tornado(d):
    rows = [r for r in d["default"]["rows"] if r["impact"] > 0.005]
    rows.sort(key=lambda r: r["impact"])
    y = np.arange(len(rows))
    lo = np.array([r["lo"] * 100 for r in rows])
    hi = np.array([r["hi"] * 100 for r in rows])

    fig, ax = plt.subplots(figsize=(9.0, 6.4))
    ax.barh(y, lo, 0.62, color=DOWN, edgecolor="white", linewidth=0.6, label="系数 ×0.75")
    ax.barh(y, hi, 0.62, color=UP, edgecolor="white", linewidth=0.6, label="系数 ×1.25")
    ax.axvline(0, color="#444", lw=0.9)

    ax.set_yticks(y)
    ax.set_yticklabels([r["name"] for r in rows], fontsize=9)
    for tick, r in zip(ax.get_yticklabels(), rows):
        tick.set_color(GROUP_COLOR.get(r["group"], INK))
    ax.set_xlabel("九个配方的平均 S 变化（%）", fontsize=10, color=INK)
    ax.set_title("哪些系数最要紧：单个系数 ±25% 对结果的影响", fontsize=12, color=INK, pad=10)
    ax.grid(axis="x", lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=9, colors=DIM)

    handles = [plt.Rectangle((0, 0), 1, 1, color=DOWN), plt.Rectangle((0, 0), 1, 1, color=UP)]
    labels = ["系数 ×0.75", "系数 ×1.25"]
    for g, c in GROUP_COLOR.items():
        if any(r["group"] == g for r in rows):
            handles.append(plt.Rectangle((0, 0), 1, 1, color=c))
            labels.append(g)
    ax.legend(handles, labels, fontsize=8, frameon=False, ncol=4,
              loc="upper center", bbox_to_anchor=(0.5, -0.10))
    fig.savefig(os.path.join(OUT, "sens_tornado.png"))
    plt.close(fig)


def fig_zones(d):
    rep = d["default"]["rep_spells"]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.2),
                             gridspec_kw={"width_ratios": [1.55, 1]})

    # 左：代表法术的单份成本
    ax = axes[0]
    names = [NAME_FIX.get(r["id"], r["name"]) for r in rep]
    x = np.arange(len(rep))
    w = 0.26
    for k, z in enumerate(("holy", "fungi", "hell")):
        vals = [r[z] if r[z] is not None else np.nan for r in rep]
        ax.bar(x + (k - 1) * w, vals, w, color=ZONE_COLOR[z], edgecolor="white",
               linewidth=0.6, label=ZONE_CN[z])
    ax.set_yscale("log")
    top = max(v for r in rep for v in (r["holy"], r["fungi"], r["hell"]) if v is not None)
    ax.set_ylim(30, top * 4.0)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=8.5, rotation=18, ha="right")
    ax.set_ylabel("单份成本（时间单位，对数轴）", fontsize=9.5, color=INK)
    ax.set_title("同一个法术，三个刷点的单价不同", fontsize=11, color=INK)
    ax.legend(fontsize=8.5, frameon=False, ncol=3, loc="upper left")
    ax.grid(axis="y", lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)

    # 右：每轮产出与单轮耗时
    ax = axes[1]
    cost = d["default"]["derived"]["cost"]
    draws = d["default"]["derived"]["draws"]
    zs = ("holy", "fungi", "hell")
    xs = np.arange(3)
    w2 = 0.34
    dr = [draws[z] for z in zs]
    co = [cost[z] for z in zs]
    b1 = ax.bar(xs - w2 / 2, dr, w2, color="#9aa3b8", edgecolor="white", linewidth=0.6,
                label="每轮抽取数（次）")
    ax2 = ax.twinx()
    b2 = ax2.bar(xs + w2 / 2, co, w2, color="#5b5bd6", edgecolor="white", linewidth=0.6,
                 label="单轮时间代价")
    for xx, v in zip(xs - w2 / 2, dr):
        ax.text(xx, v + max(dr) * 0.02, "%.0f" % v, ha="center", fontsize=7.5, color=DIM)
    for xx, v in zip(xs + w2 / 2, co):
        ax2.text(xx, v + max(co) * 0.02, "%.0f" % v, ha="center", fontsize=7.5, color="#5b5bd6")
    ax.set_xticks(xs)
    ax.set_xticklabels([ZONE_CN[z] for z in zs], fontsize=9.5)
    ax.set_ylabel("每轮抽取数", fontsize=9.5, color=INK)
    ax2.set_ylabel("单轮时间代价", fontsize=9.5, color=INK)
    ax.set_title("一轮的产出与时间代价都不相等", fontsize=11, color=INK)
    ax.set_ylim(0, max(dr) * 1.25)
    ax2.set_ylim(0, max(co) * 1.25)
    hs = [b1, b2]
    ax.legend(hs, [h.get_label() for h in hs], fontsize=8, frameon=False, loc="upper left")

    for a in (ax, ax2):
        for sp in ("top",):
            a.spines[sp].set_visible(False)
        a.tick_params(labelsize=9, colors=DIM)
    fig.savefig(os.path.join(OUT, "sens_zones.png"))
    plt.close(fig)


def fig_rounds(d):
    rows = d["default"]["rounds_vs_time"]["rows"]
    names = [r["name"].replace("tentacle", "触手").replace("blackflash", "黑闪").replace("phase", "相位")
             for r in rows]
    x = np.arange(len(rows))
    w = 0.38
    t1 = [r["time_opt"] for r in rows]
    t2 = [r["rounds_opt_time"] for r in rows]

    fig, ax = plt.subplots(figsize=(9.2, 3.8))
    ax.bar(x - w / 2, t1, w, color="#5b5bd6", edgecolor="white", linewidth=0.6,
           label="按时间最优分配")
    ax.bar(x + w / 2, t2, w, color="#d4763a", edgecolor="white", linewidth=0.6,
           label="按「总轮数最少」分配")
    for xx, a, b in zip(x, t1, t2):
        if b / a > 1.03:
            ax.text(xx, max(a, b) * 1.03, "×%.2f" % (b / a), ha="center", fontsize=8,
                    color="#c0562a")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=8.5, rotation=15, ha="right")
    ax.set_ylabel("估计时间代价", fontsize=9.5, color=INK)
    ax.set_title("只追求「轮数最少」会让时间代价变高（默认模式相位页高 47%）", fontsize=12, color=INK, pad=10)
    ax.legend(fontsize=9, frameon=False, ncol=2, loc="upper left")
    ax.grid(axis="y", lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=9, colors=DIM)
    ax.set_ylim(0, max(t2) * 1.22)
    fig.savefig(os.path.join(OUT, "sens_rounds.png"))
    plt.close(fig)


def fig_mode(d):
    """默认 vs 熟练：每抽成本趋于接近，轮数误差随之变小。"""
    m = d["modes"]
    zs = ("holy", "fungi", "hell")
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.6),
                             gridspec_kw={"width_ratios": [1.5, 1]})

    ax = axes[0]
    x = np.arange(3)
    w = 0.34
    a = [m["default"]["per_draw"][z] for z in zs]
    b = [m["expert"]["per_draw"][z] for z in zs]
    ax.bar(x - w / 2, a, w, color="#9aa3b8", edgecolor="white", linewidth=0.6, label="默认")
    ax.bar(x + w / 2, b, w, color="#5b5bd6", edgecolor="white", linewidth=0.6, label="熟练")
    for xx, v in zip(x - w / 2, a):
        ax.text(xx, v + 0.08, "%.2f" % v, ha="center", fontsize=8, color=DIM)
    for xx, v in zip(x + w / 2, b):
        ax.text(xx, v + 0.08, "%.2f" % v, ha="center", fontsize=8, color="#5b5bd6")
    ax.set_xticks(x)
    ax.set_xticklabels([ZONE_CN[z] for z in zs], fontsize=9.5)
    ax.set_ylabel("每抽成本（时间单位 / 次）", fontsize=9.5, color=INK)
    ax.set_title("熟练后三个刷点的单价趋于接近", fontsize=11, color=INK)
    ax.legend(fontsize=8.5, frameon=False, loc="upper right")
    ax.set_ylim(0, max(a + b) * 1.3)
    ax.grid(axis="y", lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)

    ax = axes[1]
    vals = [m["default"]["ratio_rounds"], m["expert"]["ratio_rounds"]]
    bars = ax.bar([0, 1], vals, 0.45, color=["#9aa3b8", "#5b5bd6"], edgecolor="white", linewidth=0.6)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, "×%.2f" % v, ha="center", fontsize=9, color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["默认", "熟练"], fontsize=9.5)
    ax.set_ylabel("「轮数最优」÷「时间最优」", fontsize=9.5, color=INK)
    ax.set_title("只数轮数的误差随之缩小", fontsize=11, color=INK)
    ax.set_ylim(0, max(vals) * 1.35)
    ax.axhline(1.0, color="#d14343", lw=1.0, ls="--")
    ax.grid(axis="y", lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)

    for a_ in axes:
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
        a_.tick_params(labelsize=9, colors=DIM)
    fig.savefig(os.path.join(OUT, "sens_mode.png"))
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    d = load()
    fig_tornado(d)
    fig_zones(d)
    fig_rounds(d)
    fig_mode(d)
    for f in ("sens_tornado", "sens_zones", "sens_rounds", "sens_mode"):
        p = os.path.join(OUT, f + ".png")
        print("  %s  %d KB" % (p, os.path.getsize(p) // 1024))


if __name__ == "__main__":
    main()
