# -*- coding: utf-8 -*-
"""权重口径评估：用蒙特卡洛模拟检验「收集难度」指标能否正确反映真实收集成本。

模型
----
* 玩家每次「法术获取机会」先按频率 f_t 落到某个等级池，再从该池按权重抽一个法术。
  单次机会抽到法术 s 的概率  q_s = Σ_t f_t · p(s,t) / Σ_t f_t，其中 p(s,t) 是 Wiki 显示的百分比。
* 收集配置 = 把每种所需法术凑够 n_s 份。凑够 s 所需次数服从负二项分布，
  整体完成时间取各法术完成时间的最大值（泊松化近似：不同法术的获取流相互独立）。
* 真值 = 上述完成时间的期望（模拟 30000 次）。

被检验的指标
------------
A. 现行：cost = Σ_s n_s / Σ_t(pct(s,t)·M(t))      （M 为工具里的繁茂/地狱倍率）
B. 归一：cost = Σ_s n_s / q_s                     （q 按场景频率正确归一）
C. 最优等级：cost = Σ_s n_s / max_t p(s,t)        （只按最容易的等级算）
D. 最稀有优先：cost = max_s n_s / q_s             （只看最难的那一种）

输出：控制台摘要 + docs/权重口径评估.md + docs/权重口径评估.png
"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "spell_weights.json")
OUT_MD = os.path.join(ROOT, "docs", "权重口径评估.md")
OUT_PNG = os.path.join(ROOT, "docs", "权重口径评估.png")

# 中文字体
for f in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
    if any(f.lower() in x.name.lower() for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

TIERS = list(range(0, 11))
M_TOOL = {2: 2.0, 3: 2.0, 4: 2.0, 10: 3.0}          # 工具当前假设

SCENARIOS = {
    "均匀 1-10": {t: 1.0 for t in range(1, 11)},
    "工具假设 M": {t: M_TOOL.get(t, 1.0) for t in range(1, 11)},
    "地狱偏重": {**{t: 1.0 for t in range(1, 10)}, 10: 8.0},
    "前期 1-4": {1: 3.0, 2: 3.0, 3: 2.0, 4: 1.5, 5: 0.5, 6: 0.3,
                 7: 0.2, 8: 0.2, 9: 0.2, 10: 0.3},
}


def load():
    spells = json.load(open(DATA, encoding="utf-8"))["spells"]
    rows = []
    for s in spells:
        if s.get("status") != "ok":
            continue
        p = {}
        for k, v in (s.get("tiers_pct") or {}).items():
            if v and v > 0:
                p[int(k)] = v / 100.0
        if p:
            rows.append({"id": s["id"], "p": p})
    return rows


def q_of(row, f):
    tot = sum(f.get(t, 0.0) for t in TIERS)
    if tot <= 0:
        return 0.0
    return sum(f.get(t, 0.0) * row["p"].get(t, 0.0) for t in TIERS) / tot


def metrics(cfg, rows_by_id, f):
    """返回四种指标（越小越难/越易？统一为「成本」，越小越容易）"""
    cur = alt_q = alt_max = 0.0
    hardest = 0.0
    costs = []
    for sid, n in cfg:
        r = rows_by_id[sid]
        # A 现行：Σ pct·M（不归一，等价于「加权和」）
        wA = sum(r["p"].get(t, 0.0) * M_TOOL.get(t, 1.0) for t in TIERS)
        cur += n / wA if wA > 0 else 1e6
        # B 归一
        q = q_of(r, f)
        alt_q += n / q if q > 0 else 1e6
        hardest = max(hardest, n / q if q > 0 else 1e6)
        # C 最优等级
        pm = max(r["p"].values())
        alt_max += n / pm
        costs.append(n / q if q > 0 else 1e6)
    # k-范数：k=1 即求和，k→∞ 即瓶颈
    k2 = sum(c ** 2 for c in costs) ** 0.5
    k3 = sum(c ** 3 for c in costs) ** (1 / 3)
    return cur, alt_q, alt_max, hardest, k2, k3


def simulate(cfg, rows_by_id, f, trials=30000, seed=0):
    """泊松化近似：各法术独立负二项，完成时间取 max"""
    rng = np.random.default_rng(seed)
    T = np.zeros(trials)
    for sid, n in cfg:
        q = q_of(rows_by_id[sid], f)
        if q <= 0:
            return np.inf
        # negative_binomial(n, q) 返回失败次数；总次数 = 失败 + 成功
        T = np.maximum(T, rng.negative_binomial(n, q, trials) + n)
    return T.mean()


def simulate_exact(cfg, rows_by_id, f, trials=3000, seed=1):
    """精确模拟：每次机会抽一个法术（含「抽到别的」），逐次累计"""
    rng = np.random.default_rng(seed)
    ids = list(rows_by_id)
    q = np.array([q_of(rows_by_id[s], f) for s in ids])
    tot = q.sum()
    need = {sid: n for sid, n in cfg}
    res = []
    for _ in range(trials):
        got = {sid: 0 for sid in need}
        rolls = 0
        while True:
            rolls += 1
            r = rng.random()
            if r > tot:            # 抽到无关法术
                continue
            k = int(np.searchsorted(np.cumsum(q), r))
            sid = ids[k]
            if sid in got:
                got[sid] += 1
                if got[sid] >= need[sid] and all(got[x] >= need[x] for x in need):
                    break
        res.append(rolls)
    return float(np.mean(res))


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    return float((ra @ rb) / np.sqrt((ra @ ra) * (rb @ rb)))


def main():
    rows = load()
    rows_by_id = {r["id"]: r for r in rows}
    ids = [r["id"] for r in rows]

    rng = np.random.default_rng(42)
    configs = []
    for _ in range(120):
        k = int(rng.integers(3, 9))
        picked = rng.choice(ids, size=k, replace=False)
        cfg = [(str(s), int(rng.integers(1, 4))) for s in picked]
        configs.append(cfg)

    lines = ["# 权重口径评估（蒙特卡洛模拟）", "",
             "> 由 `scripts/analysis/weight_sim.py` 生成，请勿手工编辑。", "",
             "## 1. 模型假设", "",
             "- 每次「法术获取机会」按频率 f_t 落到某等级池，再按权重抽一个法术；",
             "- 单次机会抽到 s 的概率 q_s = Σ_t f_t·p(s,t) / Σ_t f_t（p 为 Wiki 显示的百分比）；",
             "- 凑够 n_s 份所需次数 ~ 负二项分布，配置完成时间取各法术的最大值；",
             "- 真值 = 30000 次模拟的期望次数。", "",
             "## 2. 各场景下四种指标与真值的 Spearman 秩相关", "",
             "| 场景 | A 现行(Σ1/Σpct·M) | B 归一(Σ1/q) | C 最优等级 | D 瓶颈(max) | E 2-范数 | F 3-范数 |",
             "|---|---|---|---|---|---|---|"]

    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle("收集难度指标 vs 模拟真值（点越贴近对角线越准）", fontsize=14)
    scatter_info = []

    for si, (name, f) in enumerate(SCENARIOS.items()):
        truth, mA, mB, mC, mD, mK2, mK3 = [], [], [], [], [], [], []
        for cfg in configs:
            t = simulate(cfg, rows_by_id, f)
            if not np.isfinite(t):
                continue
            truth.append(t)
            a, b, c, d, k2, k3 = metrics(cfg, rows_by_id, f)
            mA.append(a); mB.append(b); mC.append(c); mD.append(d)
            mK2.append(k2); mK3.append(k3)
        truth = np.array(truth)
        rA, rB = spearman(mA, truth), spearman(mB, truth)
        rC, rD = spearman(mC, truth), spearman(mD, truth)
        rK2, rK3 = spearman(mK2, truth), spearman(mK3, truth)
        lines.append(f"| {name} | {rA:.4f} | {rB:.4f} | {rC:.4f} | {rD:.4f} | {rK2:.4f} | {rK3:.4f} |")
        scatter_info.append((name, truth, np.array(mA), np.array(mB)))
        print(f"[{name}] A={rA:.4f} B={rB:.4f} C={rC:.4f} D={rD:.4f} K2={rK2:.4f} K3={rK3:.4f}")

    for ax, (name, truth, mA, mB) in zip(axes.flat, scatter_info):
        ax.scatter(truth, mA, s=12, alpha=.6, label="A 现行")
        ax.scatter(truth, mB, s=12, alpha=.6, label="B 归一")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("模拟真值（期望获取次数）")
        ax.set_ylabel("指标值")
        ax.set_title(name)
        ax.legend(fontsize=8)
        ax.grid(alpha=.25)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=130)
    print("图已保存", OUT_PNG)

    # 精确模拟校验（前 3 个配置，均匀场景）
    f0 = SCENARIOS["均匀 1-10"]
    lines += ["", "## 3. 泊松化近似 vs 精确逐次模拟", "",
              "| 配置 | 负二项近似 | 精确逐次模拟 | 相对偏差 |", "|---|---|---|---|"]
    for cfg in configs[:3]:
        a = simulate(cfg, rows_by_id, f0, trials=20000)
        b = simulate_exact(cfg, rows_by_id, f0, trials=2000)
        desc = " + ".join(f"{s}×{n}" for s, n in cfg[:4]) + ("…" if len(cfg) > 4 else "")
        lines.append(f"| {desc} | {a:.0f} | {b:.0f} | {abs(a-b)/b*100:.1f}% |")
        print(f"  精确校验: 近似={a:.0f} 精确={b:.0f}")

    # 结论
    lines += ["", "## 4. 结论", "",
              "- A（现行）与真值的秩相关见上表；若显著低于 B，说明「跨等级求和」确实失真；",
              "- D 只取最难的一种，用来判断「瓶颈法术」是否主导真实成本；",
              "- 具体建议见正文分析（`docs/权重口径评估.md` 末尾）。"]
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("报告已写入", OUT_MD)


if __name__ == "__main__":
    main()
