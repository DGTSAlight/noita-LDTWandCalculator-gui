# -*- coding: utf-8 -*-
"""把 compare_v7.py 的结果画成图（供 docs/口径演进一览.md 与讲解页使用）。

输出到 docs/charts/：
  scheme_ratio.png    四个方案的「仿真时间 ÷ 口径值」比值
  scheme_metrics.png  变异系数与秩相关
  scheme_fit.png      现行方案的 S 与仿真时间散点
  scheme_stage.png    各方案把时间分到哪个刷点

用法：python scripts/analysis/plot_scheme_compare.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "parsed", "scheme_compare.json")
OUT = os.path.join(ROOT, "docs", "charts")

# 中文字体
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
ACCENT = "#5b5bd6"

# 四个方案：由浅到深，表示时间上从旧到新
SCHEMES = ["S1", "S2", "S3", "S4"]
COLORS = ["#c8ccd6", "#9aa3b8", "#6f7fa8", ACCENT]
ZONE_CN = {"holy": "圣山", "fungi": "繁茂", "hell": "地狱"}
ZONE_COLOR = {"holy": "#e0b252", "fungi": "#5aa469", "hell": "#b5546a"}


def load():
    d = json.load(open(DATA, encoding="utf-8"))
    return d


def short(name):
    page, lvl = name.split("/")
    return {"tentacle": "触手", "blackflash": "黑闪", "phase": "相位"}[page] + lvl


def fig_ratio(d):
    names = [short(n) for n in d["names"]]
    x = np.arange(len(names))
    w = 0.2
    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    for k, (sch, c) in enumerate(zip(SCHEMES, COLORS)):
        r = d["schemes"][sch]["ratio"]
        ax.bar(x + (k - 1.5) * w, r, w, label=d["label"][sch], color=c, edgecolor="white", linewidth=0.6)
    ax.axhline(1.0, color="#d14343", lw=1.4, ls="--", zorder=5, label="理想值 1.00")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("仿真时间 ÷ 口径值", fontsize=10, color=INK)
    ax.set_title("四个方案对同一批配方的标度偏差", fontsize=12, color=INK, pad=10)
    ax.legend(fontsize=8.5, frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    ax.grid(axis="y", lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=9, colors=DIM)
    fig.savefig(os.path.join(OUT, "scheme_ratio.png"))
    plt.close(fig)


def fig_metrics(d):
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    labels = [d["label"][s] for s in SCHEMES]
    x = np.arange(len(SCHEMES))

    ax = axes[0]
    cv = [d["schemes"][s]["cv"] for s in SCHEMES]
    ax.bar(x, cv, 0.55, color=COLORS, edgecolor="white", linewidth=0.6)
    for i, v in enumerate(cv):
        ax.text(i, v + 0.006, f"{v:.3f}", ha="center", fontsize=9, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([l.replace("（现行）", "\n（现行）") for l in labels], fontsize=8.5)
    ax.set_ylabel("变异系数（越小越稳）", fontsize=10, color=INK)
    ax.set_title("同一把尺子的稳定性", fontsize=11, color=INK)
    ax.set_ylim(0, max(cv) * 1.25)

    ax = axes[1]
    rho = [d["schemes"][s]["rho_all"] for s in SCHEMES]
    ax.bar(x, rho, 0.55, color=COLORS, edgecolor="white", linewidth=0.6)
    for i, v in enumerate(rho):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=9, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([l.replace("（现行）", "\n（现行）") for l in labels], fontsize=8.5)
    ax.set_ylabel("Spearman 秩相关", fontsize=10, color=INK)
    ax.set_title("与仿真排序的一致程度", fontsize=11, color=INK)
    ax.set_ylim(0, 1.05)

    for ax in axes:
        ax.grid(axis="y", lw=0.7, alpha=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=9, colors=DIM)
    fig.savefig(os.path.join(OUT, "scheme_metrics.png"))
    plt.close(fig)


def fig_fit(d):
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    truth = d["truth"]["default"]
    s = d["schemes"]["S4"]["S"]
    ax.scatter(s, truth, s=54, color=ACCENT, edgecolor="white", linewidth=0.8, zorder=3,
               label="默认模式")
    te = d["expert"]["truth"]
    se = d["expert"]["S"]
    ax.scatter(se, te, s=54, color="#5aa469", edgecolor="white", linewidth=0.8, zorder=3,
               marker="s", label="熟练模式")

    lo, hi = 600, 4800
    ax.plot([lo, hi], [lo, hi], color="#d14343", lw=1.2, ls="--", zorder=2)
    ax.text(hi * 0.97, hi * 1.03, "y = x", color="#d14343", fontsize=9, ha="right")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("口径值 S（时间单位）", fontsize=10, color=INK)
    ax.set_ylabel("仿真中位时间", fontsize=10, color=INK)
    ax.set_title("现行方案：口径值与仿真时间", fontsize=12, color=INK, pad=10)
    ax.legend(fontsize=9, frameon=False, loc="upper left")
    ax.grid(lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=9, colors=DIM)
    fig.savefig(os.path.join(OUT, "scheme_fit.png"))
    plt.close(fig)


def fig_stage(d):
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    labels = [d["label"][s] for s in SCHEMES]
    x = np.arange(len(SCHEMES))
    bottom = np.zeros(len(SCHEMES))
    for z in ("holy", "fungi", "hell"):
        share = []
        for sch in SCHEMES:
            tot = [sum(row.values()) for row in d["schemes"][sch]["stage"]]
            part = [row[z] for row in d["schemes"][sch]["stage"]]
            share.append(np.mean([p / t for p, t in zip(part, tot)]))
        share = np.array(share)
        ax.bar(x, share, 0.55, bottom=bottom, color=ZONE_COLOR[z], edgecolor="white",
               linewidth=0.8, label=ZONE_CN[z])
        for i, v in enumerate(share):
            if v > 0.06:
                ax.text(i, bottom[i] + v / 2, f"{v*100:.0f}%", ha="center", va="center",
                        fontsize=9, color="white")
        bottom += share
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_ylabel("时间占比（9 个配方平均）", fontsize=10, color=INK)
    ax.set_title("同一批配方，各方案把时间分给哪个刷点", fontsize=12, color=INK, pad=10)
    ax.legend(fontsize=9, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=9, colors=DIM)
    fig.savefig(os.path.join(OUT, "scheme_stage.png"))
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    d = load()
    fig_ratio(d)
    fig_metrics(d)
    fig_fit(d)
    fig_stage(d)
    for f in ("scheme_ratio", "scheme_metrics", "scheme_fit", "scheme_stage"):
        p = os.path.join(OUT, f + ".png")
        print(f"  {p}  {os.path.getsize(p)//1024} KB")


if __name__ == "__main__":
    main()
