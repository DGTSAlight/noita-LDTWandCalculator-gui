# -*- coding: utf-8 -*-
"""按「搜法术策略」对计算器给出的配方做蒙特卡洛仿真，检验相对难度（S值）口径。

用法：
    node tests/_dump_recipes.js > tests/_recipes.json
    /d/lerning/pylearning/envs/new01/python.exe scripts/analysis/strategy_sim.py

模型
----
把「去哪里刷」抽象成三个**搜索模式**（把区间内所有等级当成同一个池子）：

    繁茂 = 2/3/4 级     地狱 = 10 级     均匀 = 0~10 级

- 每次抽取：在模式内**均匀**选一个等级，再按该等级的条件概率 pct(s,t)/100 命中法术 s
  → p_G(s) = Σ_{t∈G} pct(s,t)/100 / |G|
- 模式的效率倍率 E_G = mean(M(t) for t in G)，M 是界面上的「繁茂/地狱倍率」
  → 花的时间 = 抽取次数 / E_G

一次收集的时间 T = Σ_阶段 ( max_s T_s / E_阶段 )，T_s ~ 负二项（拿到 n_s 份所需次数）。

四种策略
--------
uniform      一次到底，均匀抽
fungal_first 先繁茂（收齐所有有 2/3/4 权重的法术）→ 80% 地狱 + 20% 均匀
hell_first   先地狱（收齐所有有 10 级权重的法术）→ 80% 繁茂 + 20% 均匀
greedy       与「分组口径」完全一致：每次挑「总权重最大」的模式刷完再换

三种口径对比
------------
S_now    现行：q(s)=Σ_t M(t)·pct/100（各等级并行），3-范数
S_max    旧 max：q(s)=max_t M(t)·pct/100（每个法术各挑最有利等级），3-范数
S_group  新分组：按模式贪心排序，阶段内 3-范数，阶段间求和（本次要评估的）
"""
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRIALS = 20000

FUNGAL = [2, 3, 4]
HELL = [10]
ALL_TIERS = list(range(11))
MODES = [("繁茂", FUNGAL), ("地狱", HELL), ("均匀", ALL_TIERS)]
MULT = {2: 2.0, 3: 2.0, 4: 2.0, 10: 3.0}


def load():
    data = json.load(open(os.path.join(ROOT, "data", "spell_weights.json"), encoding="utf-8"))
    pct = {}
    for s in data["spells"]:
        row = np.zeros(11)
        for t, v in (s.get("tiers_pct") or {}).items():
            if v and v > 0:
                row[int(t)] = v / 100.0
        pct[s["id"]] = row
    recs = json.load(open(os.path.join(ROOT, "tests", "_recipes.json"), encoding="utf-8"))
    return pct, recs


def p_of(pct, sid, tiers):
    """模式 tiers 内每次抽取命中 sid 的概率（模式内等级均匀）。"""
    return float(pct[sid][tiers].sum() / len(tiers))


def eff(tiers):
    """模式效率：模式内各等级倍率的平均。"""
    return float(np.mean([MULT.get(t, 1.0) for t in tiers]))


def p_mix(pct, sid, parts):
    """混合模式：parts = [(tiers, 权重)]"""
    return sum(w * p_of(pct, sid, ts) for ts, w in parts)


def eff_mix(parts):
    return sum(w * eff(ts) for ts, w in parts)


# ---------------------------------------------------------------- 蒙特卡洛
def sim_phase(items, p, e, rng):
    """items=[(sid,n)]；返回该阶段的期望时间 = E[max NB] / e"""
    if not items:
        return 0.0
    Ts = np.empty((TRIALS, len(items)))
    for j, (sid, n) in enumerate(items):
        Ts[:, j] = rng.negative_binomial(n, p[sid], size=TRIALS) + n
    return float(Ts.max(axis=1).mean() / e)


def run_strategy(pct, need, kind, rng):
    ids = [x["id"] for x in need]
    cnt = {x["id"]: x["lack"] for x in need}

    def has(sid, tiers):
        return pct[sid][tiers].sum() > 0

    if kind == "uniform":
        p = {s: p_of(pct, s, ALL_TIERS) for s in ids}
        return sim_phase([(s, cnt[s]) for s in ids], p, eff(ALL_TIERS), rng), "均匀"

    if kind == "greedy":
        remaining = list(ids)
        total, order = 0.0, []
        while remaining:
            best, bestW = None, -1.0
            for name, tiers in MODES:
                if name in order:
                    continue
                W = sum(cnt[s] * p_of(pct, s, tiers) * eff(tiers) for s in remaining)
                if W > bestW:
                    bestW, best = W, (name, tiers)
            name, tiers = best
            order.append(name)
            got = [s for s in remaining if p_of(pct, s, tiers) > 0]
            if not got:
                continue
            total += sim_phase([(s, cnt[s]) for s in got],
                               {s: p_of(pct, s, tiers) for s in got}, eff(tiers), rng)
            remaining = [s for s in remaining if s not in got]
        return total, "→".join(order)

    if kind == "assign_opt":
        # 与引擎一致：先各自最有利，再最速下降，目标是「阶段间求和」的 S 最小
        G = len(MODES)
        cost = {}
        for s in ids:
            cost[s] = [cnt[s] / (p_of(pct, s, tiers) * eff(tiers))
                       if p_of(pct, s, tiers) > 0 else 1e18 * cnt[s]
                       for _, tiers in MODES]
        assign = {}
        acc = [0.0] * G
        for s in ids:
            b = min(range(G), key=lambda g: cost[s][g])
            assign[s] = b
            acc[b] += cost[s][b] ** 3
        total_s = sum(a ** (1 / 3) for a in acc)
        for _ in range(24):
            best_d, bi, bg = -1e-9, None, None
            for s in ids:
                f = assign[s]
                for g in range(G):
                    if g == f:
                        continue
                    a1 = max(0.0, acc[f] - cost[s][f] ** 3)
                    a2 = acc[g] + cost[s][g] ** 3
                    nt = total_s - acc[f] ** (1 / 3) - acc[g] ** (1 / 3) \
                        + a1 ** (1 / 3) + a2 ** (1 / 3)
                    if nt - total_s < best_d:
                        best_d, bi, bg = nt - total_s, s, g
            if bi is None:
                break
            acc[assign[bi]] -= cost[bi][assign[bi]] ** 3
            assign[bi] = bg
            acc[bg] += cost[bi][bg] ** 3
            total_s += best_d
        groups = {}
        for s in ids:
            groups.setdefault(assign[s], []).append(s)
        order = sorted(groups, key=lambda g: -sum(cnt[s] * p_of(pct, s, MODES[g][1]) * eff(MODES[g][1])
                                                 for s in groups[g]))
        total = 0.0
        for g in order:
            tiers, lst = MODES[g][1], groups[g]
            total += sim_phase([(s, cnt[s]) for s in lst],
                               {s: p_of(pct, s, tiers) for s in lst}, eff(tiers), rng)
        return total, "→".join(MODES[g][0] for g in order)

    if kind == "greedy2":
        # 每个法术先指派到「自己最有利」的模式，再按模式总权重排序，逐阶段刷
        assign = {}
        for s in ids:
            bestG, bestR = None, -1.0
            for name, tiers in MODES:
                r = p_of(pct, s, tiers) * eff(tiers)
                if r > bestR:
                    bestR, bestG = r, (name, tiers)
            assign[s] = bestG
        groups = {}
        for s in ids:
            groups.setdefault(assign[s][0], (assign[s][1], []))[1].append(s)
        order = sorted(groups, key=lambda g: -sum(cnt[s] * p_of(pct, s, groups[g][0]) * eff(groups[g][0])
                                                 for s in groups[g][1]))
        total = 0.0
        for g in order:
            tiers, lst = groups[g]
            total += sim_phase([(s, cnt[s]) for s in lst],
                               {s: p_of(pct, s, tiers) for s in lst}, eff(tiers), rng)
        return total, "→".join(order)

    if kind == "fungal_first":
        p1 = [s for s in ids if has(s, FUNGAL)]
        p2 = [s for s in ids if s not in p1]
        mix = [(HELL, 0.8), (ALL_TIERS, 0.2)]
        note = "繁茂(%d)→80%%地狱+20%%均匀(%d)" % (len(p1), len(p2))
        t = sim_phase([(s, cnt[s]) for s in p1], {s: p_of(pct, s, FUNGAL) for s in p1},
                      eff(FUNGAL), rng)
    else:  # hell_first
        p1 = [s for s in ids if has(s, HELL)]
        p2 = [s for s in ids if s not in p1]
        mix = [(FUNGAL, 0.8), (ALL_TIERS, 0.2)]
        note = "地狱(%d)→80%%繁茂+20%%均匀(%d)" % (len(p1), len(p2))
        t = sim_phase([(s, cnt[s]) for s in p1], {s: p_of(pct, s, HELL) for s in p1},
                      eff(HELL), rng)
    if p2:
        t += sim_phase([(s, cnt[s]) for s in p2], {s: p_mix(pct, s, mix) for s in p2},
                       eff_mix(mix), rng)
    return t, note


# ---------------------------------------------------------------- 三种口径
def s_now(pct, need):
    """现行：各等级并行求和"""
    acc = 0.0
    for x in need:
        q = sum(MULT.get(t, 1.0) * pct[x["id"]][t] for t in ALL_TIERS)
        c = (x["lack"] / q) if q > 0 else 1e18
        acc += c ** 3
    return acc ** (1 / 3)


def s_max(pct, need):
    """旧 max：每个法术各挑最有利的单个等级"""
    acc = 0.0
    for x in need:
        q = max(MULT.get(t, 1.0) * pct[x["id"]][t] for t in ALL_TIERS)
        c = (x["lack"] / q) if q > 0 else 1e18
        acc += c ** 3
    return acc ** (1 / 3)


def s_group(pct, need, trace=False):
    """新分组：按模式贪心排序，阶段内 3-范数，阶段间求和"""
    remaining = list(need)
    used, total, order = set(), 0.0, []
    while remaining:
        best, bestW = None, -1.0
        for name, tiers in MODES:
            if name in used:
                continue
            W = sum(x["lack"] * p_of(pct, x["id"], tiers) * eff(tiers) for x in remaining)
            if W > bestW:
                bestW, best = W, (name, tiers)
        name, tiers = best
        used.add(name)
        got = [x for x in remaining if p_of(pct, x["id"], tiers) > 0]
        if not got:
            continue
        acc = 0.0
        for x in got:
            c = x["lack"] / (p_of(pct, x["id"], tiers) * eff(tiers))
            acc += c ** 3
        total += acc ** (1 / 3)
        order.append(name)
        remaining = [x for x in remaining if x not in got]
    return (total, "→".join(order)) if trace else total


def s_group2(pct, need, trace=False):
    """分组 v2：每个法术先指派到「自己最有利」的模式，再按模式总权重排序分阶段求和"""
    assign = {}
    for x in need:
        sid = x["id"]
        bestG, bestR = None, -1.0
        for name, tiers in MODES:
            r = p_of(pct, sid, tiers) * eff(tiers)
            if r > bestR:
                bestR, bestG = r, (name, tiers)
        assign[sid] = bestG
    groups = {}
    for x in need:
        name, tiers = assign[x["id"]]
        groups.setdefault(name, (tiers, []))[1].append(x)
    order = sorted(groups, key=lambda g: -sum(
        x["lack"] * p_of(pct, x["id"], groups[g][0]) * eff(groups[g][0]) for x in groups[g][1]))
    total = 0.0
    for g in order:
        tiers, lst = groups[g]
        acc = 0.0
        for x in lst:
            c = x["lack"] / (p_of(pct, x["id"], tiers) * eff(tiers))
            acc += c ** 3
        total += acc ** (1 / 3)
    return (total, "→".join(order)) if trace else total


def s_assign_opt(pct, need, trace=False):
    """分组 v3：指派目标改成「总 S 最小」（初值各自最有利 + 最速下降），与引擎一致"""
    G = len(MODES)
    ids = [x["id"] for x in need]
    cnt = {x["id"]: x["lack"] for x in need}
    cost = {s: [cnt[s] / (p_of(pct, s, tiers) * eff(tiers)) if p_of(pct, s, tiers) > 0
                else 1e18 * cnt[s] for _, tiers in MODES] for s in ids}
    assign, acc = {}, [0.0] * G
    for s in ids:
        b = min(range(G), key=lambda g: cost[s][g])
        assign[s] = b
        acc[b] += cost[s][b] ** 3
    total = sum(a ** (1 / 3) for a in acc)
    for _ in range(24):
        best_d, bi, bg = -1e-9, None, None
        for s in ids:
            f = assign[s]
            for g in range(G):
                if g == f:
                    continue
                a1 = max(0.0, acc[f] - cost[s][f] ** 3)
                a2 = acc[g] + cost[s][g] ** 3
                nt = total - acc[f] ** (1 / 3) - acc[g] ** (1 / 3) + a1 ** (1 / 3) + a2 ** (1 / 3)
                if nt - total < best_d:
                    best_d, bi, bg = nt - total, s, g
        if bi is None:
            break
        acc[assign[bi]] -= cost[bi][assign[bi]] ** 3
        assign[bi] = bg
        acc[bg] += cost[bi][bg] ** 3
        total += best_d
    if trace:
        names = sorted({MODES[assign[s]][0] for s in ids},
                       key=lambda n: -sum(MODES[assign[s]][1] is MODES[[m[0] for m in MODES].index(n)][1]
                                          and cnt[s] * p_of(pct, s, MODES[[m[0] for m in MODES].index(n)][1])
                                          * eff(MODES[[m[0] for m in MODES].index(n)][1]) for s in ids))
        return total, "→".join(names)
    return total


def spearman(a, b):
    def rank(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return np.array(r)
    ra, rb = rank(a), rank(b)
    ra -= ra.mean(); rb -= rb.mean()
    return float((ra * rb).sum() / np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))


def main():
    pct, recs = load()
    rng = np.random.default_rng(20261028)
    KINDS = ["uniform", "fungal_first", "hell_first", "greedy", "greedy2", "assign_opt"]

    print("=" * 104)
    print("一、模式参数（繁茂/地狱倍率取界面默认 2.0 / 3.0）")
    print("=" * 104)
    for name, tiers in MODES:
        print("  %-4s 等级 %-14s |G|=%2d | 效率 E=%.3f"
              % (name, str(tiers), len(tiers), eff(tiers)))

    print()
    print("=" * 104)
    print("二、九个配方 × 四种策略的仿真时间（等效单位，已含倍率）")
    print("=" * 104)
    rows = []
    hdr = "%-10s %-4s %8s %9s %9s %9s %9s %9s %9s %9s"
    print(hdr % ("页面", "难度", "现行S", "均匀", "先繁茂", "先地狱", "分组贪心", "指派贪心", "指派最优", "最优"))
    for r in recs:
        line = {}
        for k in KINDS:
            line[k] = run_strategy(pct, r["need"], k, rng)
        rows.append((r, line))
        best = min(line[k][0] for k in KINDS)
        print(hdr % (r["page"], r["level"], "%.1f" % r["score"],
                     "%.1f" % line["uniform"][0], "%.1f" % line["fungal_first"][0],
                     "%.1f" % line["hell_first"][0], "%.1f" % line["greedy"][0],
                     "%.1f" % line["greedy2"][0], "%.1f" % line["assign_opt"][0],
                     "%.1f" % best))

    print()
    print("=" * 104)
    print("三、三种口径 vs 最优仿真")
    print("=" * 104)
    hdr2 = "%-10s %-4s %7s %7s %7s %7s %7s %9s %6s %6s %6s %6s %6s"
    print(hdr2 % ("页面", "难度", "现行S", "旧max", "分组v1", "分组v2", "分组v3",
                  "最优仿真", "S", "max", "v1", "v2", "v3"))
    rn, rm, rg, r2, r3, bests = [], [], [], [], [], []
    for r, line in rows:
        best = min(line[k][0] for k in KINDS)
        a, b = s_now(pct, r["need"]), s_max(pct, r["need"])
        c, d = s_group(pct, r["need"]), s_group2(pct, r["need"])
        e = s_assign_opt(pct, r["need"])
        rn.append(best / a); rm.append(best / b); rg.append(best / c)
        r2.append(best / d); r3.append(best / e)
        bests.append(best)
        print(hdr2 % (r["page"], r["level"], "%.1f" % a, "%.1f" % b, "%.1f" % c,
                      "%.1f" % d, "%.1f" % e, "%.1f" % best,
                      "%.2f" % (best / a), "%.2f" % (best / b),
                      "%.2f" % (best / c), "%.2f" % (best / d), "%.2f" % (best / e)))
    for label, arr in (("现行 S", rn), ("旧 max", rm), ("分组 v1", rg),
                       ("分组 v2", r2), ("分组 v3", r3)):
        arr = np.array(arr)
        print("  %-8s 比值 %.2f~%.2f  中位 %.2f  变异系数 %.3f"
              % (label, arr.min(), arr.max(), np.median(arr), arr.std() / arr.mean()))

    print()
    print("=" * 104)
    print("四、排名一致性（Spearman，与最优仿真比）")
    print("=" * 104)
    for label, vals in (("现行 S", [s_now(pct, r["need"]) for r, _ in rows]),
                        ("旧 max", [s_max(pct, r["need"]) for r, _ in rows]),
                        ("分组 v1", [s_group(pct, r["need"]) for r, _ in rows]),
                        ("分组 v2", [s_group2(pct, r["need"]) for r, _ in rows]),
                        ("分组 v3", [s_assign_opt(pct, r["need"]) for r, _ in rows])):
        print("  %-8s ρ = %.3f" % (label, spearman(vals, bests)))

    print()
    print("=" * 104)
    print("四之二、页内排名一致性（三个页签是彼此独立的工具，页内排序才是实际用途）")
    print("=" * 104)
    pages = sorted({r["page"] for r, _ in rows})
    for label, fn in (("现行 S", s_now), ("旧 max", s_max),
                      ("分组 v1", s_group), ("分组 v2", s_group2),
                      ("分组 v3", s_assign_opt)):
        rs = []
        for pg in pages:
            sel = [(r, line) for r, line in rows if r["page"] == pg]
            met = [fn(pct, r["need"]) for r, _ in sel]
            sim = [min(line[k][0] for k in KINDS) for _, line in sel]
            rs.append(spearman(met, sim))
        print("  %-8s 页内 ρ：%s  （均值 %.3f）"
              % (label, "  ".join("%s=%.2f" % (pg, v) for pg, v in zip(pages, rs)),
                 float(np.mean(rs))))

    print()
    print("=" * 104)
    print("五、分组口径给出的刷取顺序 vs 贪心仿真")
    print("=" * 104)
    for r, line in rows:
        v1, o1 = s_group(pct, r["need"], trace=True)
        v2, o2 = s_group2(pct, r["need"], trace=True)
        print("  %-10s %-2s  v1：%-16s(%.0f)  v2：%-16s(%.0f)  仿真最优：%s"
              % (r["page"], r["level"], o1, v1, o2, v2,
                 min(line, key=lambda k: line[k][0])))

    print()
    print("=" * 104)
    print("五之二、引擎现行口径（分组 v3）vs 同款策略的仿真（应接近 1.00）")
    print("=" * 104)
    print("  %-10s %-4s %9s %11s %8s %s" % ("页面", "难度", "引擎 S", "仿真 v3", "比值", "阶段"))
    ratios = []
    for r, line in rows:
        e = s_assign_opt(pct, r["need"])
        sim = line["assign_opt"][0]
        ratios.append(sim / e)
        _, order = s_group2(pct, r["need"], trace=True)
        print("  %-10s %-4s %9.1f %11.1f %8.2f %s"
              % (r["page"], r["level"], e, sim, sim / e, line["assign_opt"][1]))
    ratios = np.array(ratios)
    print("  比值 %.2f~%.2f  中位 %.2f  变异系数 %.3f"
          % (ratios.min(), ratios.max(), np.median(ratios), ratios.std() / ratios.mean()))

    print()
    print("=" * 104)
    print("六、逐配方：四种策略的明细")
    print("=" * 104)
    for r, line in rows:
        print("· %s / %s（现行S=%.1f，%s）" % (r["page"], r["level"], r["score"], r["desc"]))
        for k in KINDS:
            print("   %-13s %8.1f   %s" % (k, line[k][0], line[k][1]))
        print()


if __name__ == "__main__":
    main()
