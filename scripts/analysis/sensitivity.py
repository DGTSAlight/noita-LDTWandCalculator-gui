# -*- coding: utf-8 -*-
"""系数敏感性分析（2026-11-01）。

目的：找出当前时间代价模型里「人为主观决定」的系数各自有多重要，
      以便告诉玩家「先测哪个数最有价值」。

做法：
  1. 把模型写成「原始系数 → 三个刷点的单轮耗时 / 每轮抽取数 / 换世界成本」的推导链；
  2. 每次只把一个原始系数乘 0.75 或 1.25，重算 9 个真实配方的 S；
  3. 记录 S 相对基线的平均变化幅度，排序。

另外做一件事：对比「最小总轮数」与「最小总时间」两种目标，
说明为什么不能只用轮数（前者会退化）。

用法：python scripts/analysis/sensitivity.py
输出：data/parsed/sensitivity.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_v7 as S  # noqa: E402

ROOT = S.ROOT
OUT = os.path.join(ROOT, "data", "parsed", "sensitivity.json")
ZONES = ("holy", "fungi", "hell")

# ---------------------------------------------------------------- 原始系数
# 单位：VOID/MIXED/SOLID 是地形系数（每 512 px 行进的时间），其余见注释
BASE = {
    "VOID": 1.0,            # 空隙地形系数（基准，定义为 1）
    "MIXED": 2.0,           # 混合地形系数（洞穴/地表，要跳要绕）
    "SOLID": 4.0,           # 固体地形系数（需挖掘）
    "RUN_WAND": 4.0,        # 搜 1 区块法杖 ≈ 在该环境跑 4 区块
    "RUN_SPELL": 2.0,       # 搜 1 区块法术 ≈ 跑 2 区块
    "HOLY_GAP": 3.27,       # 相邻两座圣山的层间距离（区块）
    "P_SPELL_SHOP": 51 / 101,   # 圣山开成法术店的概率（源码）
    "HOLY_CARDS": 10.0,     # 法术店 5 摊 × 2 排（源码）
    "HOLY_WAND_COUNT": 5.0,     # 法杖店 5 根（源码）
    "CARDS_PER_WAND": 4.5,  # 每根法杖的卡数（由容量分布推导，非实测）
    "EYE_CARDS": 8.0,       # 眼睛房间 8 张（场景标记数）
    "EYE_SOLID_PX": 1500.0,     # 去眼睛房间要挖的固体
    "EYE_MIXED_PX": 2000.0,     # 去眼睛房间的混合地形
    "FUNGI_CHUNKS": 42.0,   # 上繁茂区块数
    "FUNGI_WANDS_PER_CHUNK": 72 / 42,   # 实测 72 根 / 42 区块
    "DANGER": 2.0,          # 繁茂危险惩罚（默认）
    "FUNGI_ENTRY_VOID": 4000.0,     # 圣山 → 繁茂的空隙
    "FUNGI_ENTRY_MIXED": 1500.0,    # 圣山 → 繁茂的混合
    "HELL_CHUNKS": 86.0,    # 默认模式扫整轮走廊的区块数
    "HELL_TRAVERSE": 0.0,   # 地狱两侧穿行（熟练模式 14 区块空隙）
    "HELL_CARDS": 62.5,     # 地狱一轮产出的法术卡数
    "HELL_REFILL": 43.0,    # 地狱重刷（22000 px 空隙）
    "ASCEND_PX": 13110.0,   # 从最深圣山升回地面
    "HOP_VOID_CHUNKS": 64.14,   # 跨平行世界的空隙（70 区块减去岩墙）
    "WALL_PX": 3000.0,      # 跨平行世界的岩墙
    "NORM": 3.0,            # 三范数的阶数
}

# 熟练模式：只改两个数（繁茂危险 2.0→1.5、地狱 86→10 区块 + 14 区块穿行）
EXPERT = dict(BASE, DANGER=1.5, HELL_CHUNKS=10.0, HELL_TRAVERSE=14.0)

# 中文名 + 类别（地形 / 搜索动作 / 密度 / 库存 / 换世界 / 聚合）
META = {
    "MIXED": ("混合地形系数", "地形"),
    "SOLID": ("固体地形系数", "地形"),
    "RUN_WAND": ("搜 1 区块法杖的跑图倍数", "搜索动作"),
    "RUN_SPELL": ("搜 1 区块法术的跑图倍数", "搜索动作"),
    "DANGER": ("繁茂危险惩罚", "搜索动作"),
    "CARDS_PER_WAND": ("每根法杖的卡数", "密度"),
    "FUNGI_WANDS_PER_CHUNK": ("繁茂每区块法杖数", "密度"),
    "HELL_CARDS": ("地狱每轮产卡数", "密度"),
    "HOLY_WAND_COUNT": ("圣山法杖店根数", "库存"),
    "HOLY_GAP": ("圣山层间距离", "库存"),
    "FUNGI_CHUNKS": ("上繁茂区块数", "库存"),
    "HELL_CHUNKS": ("地狱搜索区块数", "库存"),
    "HELL_TRAVERSE": ("地狱两侧穿行", "库存"),
    "HELL_REFILL": ("地狱补货成本", "库存"),
    "EYE_CARDS": ("眼睛房间卡数", "库存"),
    "EYE_SOLID_PX": ("眼睛房间固体距离", "库存"),
    "EYE_MIXED_PX": ("眼睛房间混合距离", "库存"),
    "ASCEND_PX": ("升回地面的距离", "换世界"),
    "HOP_VOID_CHUNKS": ("跨世界空隙距离", "换世界"),
    "WALL_PX": ("跨世界岩墙厚度", "换世界"),
    "FUNGI_ENTRY_VOID": ("圣山→繁茂空隙", "换世界"),
    "FUNGI_ENTRY_MIXED": ("圣山→繁茂混合", "换世界"),
    "NORM": ("范数阶数", "聚合"),
}


def derive(p):
    """由原始系数推出三个刷点的单轮耗时、每轮抽取数、换世界成本。"""
    v, m, s = p["VOID"], p["MIXED"], p["SOLID"]
    holy_search = (p["P_SPELL_SHOP"] * p["RUN_SPELL"] + (1 - p["P_SPELL_SHOP"]) * p["RUN_WAND"]) * v
    cost_holy = 6 * (p["HOLY_GAP"] * m + holy_search) \
        + (p["EYE_SOLID_PX"] / 512 * s + p["EYE_MIXED_PX"] / 512 * m)
    draws_holy = 6 * (p["P_SPELL_SHOP"] * p["HOLY_CARDS"]
                      + (1 - p["P_SPELL_SHOP"]) * p["HOLY_WAND_COUNT"] * p["CARDS_PER_WAND"]) \
        + p["EYE_CARDS"]

    cost_fungi = (p["FUNGI_CHUNKS"] * p["RUN_WAND"] * m * p["DANGER"]
                  + p["FUNGI_ENTRY_VOID"] / 512 * v + p["FUNGI_ENTRY_MIXED"] / 512 * m)
    draws_fungi = p["FUNGI_CHUNKS"] * p["FUNGI_WANDS_PER_CHUNK"] * p["CARDS_PER_WAND"]

    cost_hell = (p["HELL_CHUNKS"] * p["RUN_SPELL"] * m
                 + p["HELL_TRAVERSE"] * v + p["HELL_REFILL"])
    draws_hell = p["HELL_CARDS"]

    reset = p["ASCEND_PX"] / 512 * v + p["HOP_VOID_CHUNKS"] * v + p["WALL_PX"] / 512 * s

    return ({"holy": cost_holy, "fungi": cost_fungi, "hell": cost_hell},
            {"holy": draws_holy, "fungi": draws_fungi, "hell": draws_hell},
            reset)


def solve(need, vecs, idx, cost, draws, reset, norm=3.0):
    """按「每份成本 / 3-范数聚合 / 共享换世界」算 S。返回 (总时间, 各区域轮数)。"""
    ids = [k for k in need if k in idx]
    if not ids:
        return 0.0, {z: 0.0 for z in ZONES}
    n = len(ids)
    unit = []
    for sid in ids:
        row = {}
        for z in ZONES:
            pr = vecs[z][idx[sid]]
            row[z] = need[sid] / (draws[z] * pr) if pr > 0 else float("inf")
        unit.append(row)

    assign, acc = [], {z: 0.0 for z in ZONES}
    for i in range(n):
        b = min(ZONES, key=lambda z: unit[i][z])
        assign.append(b)
        if np.isfinite(unit[i][b]):
            acc[b] += unit[i][b] ** norm

    def total_of(a):
        ks = {z: a[z] ** (1.0 / norm) for z in ZONES}
        return (sum(ks[z] * cost[z] for z in ZONES)
                + max(ks["holy"], ks["fungi"]) * reset), ks

    cur, _ = total_of(acc)
    for _ in range(30):
        best_d, mv = -1e-9, None
        for i in range(n):
            frm = assign[i]
            for z in ZONES:
                if z == frm or not np.isfinite(unit[i][z]):
                    continue
                of, oz = acc[frm], acc[z]
                acc[frm] = max(0.0, of - (unit[i][frm] ** norm if np.isfinite(unit[i][frm]) else 0))
                acc[z] = oz + unit[i][z] ** norm
                t, _ = total_of(acc)
                acc[frm], acc[z] = of, oz
                if t - cur < best_d:
                    best_d, mv = t - cur, (i, z)
        if mv is None:
            break
        i, z = mv
        frm = assign[i]
        if np.isfinite(unit[i][frm]):
            acc[frm] = max(0.0, acc[frm] - unit[i][frm] ** norm)
        acc[z] += unit[i][z] ** norm
        assign[i] = z
        cur, _ = total_of(acc)

    t, ks = total_of(acc)
    return t, ks


def load_all():
    spells, tot_all, tot_type, project = S.load()
    vecs, idx = S.build_vectors(spells, tot_all, tot_type, project)
    recipes = json.load(open(S.RECIPES, encoding="utf-8"))
    needs = []
    for r in recipes:
        needs.append({it["id"]: it["lack"] for it in r["need"] if it["id"] in idx})
    return spells, vecs, idx, recipes, needs


def run_all(params, needs, vecs, idx):
    cost, draws, reset = derive(params)
    return [solve(nd, vecs, idx, cost, draws, reset, params["NORM"])[0] for nd in needs]


SPELL_CN = {}
REP = ["LIGHT_SHOT", "SPEED", "PHASING_ARC", "LARPA_CHAOS_2",
       "BLACK_HOLE", "ADD_TRIGGER", "DIVIDE_10"]


def analyse(params, needs, vecs, idx, recipes, tag=""):
    """对一套参数跑完整分析，返回一个可 JSON 化的块。"""
    base = run_all(params, needs, vecs, idx)
    cost0, draws0, reset0 = derive(params)
    print("[%s] 圣山 %.1f / 繁茂 %.1f / 地狱 %.1f / 换世界 %.1f"
          % (tag, cost0["holy"], cost0["fungi"], cost0["hell"], reset0))

    # ---- 单系数敏感性 ----
    rows = []
    for key in params:
        if key in ("VOID", "P_SPELL_SHOP", "NORM", "HOLY_CARDS", "HOLY_WAND_COUNT"):
            continue
        meta = META.get(key, (key, "其它"))
        rec = {"key": key, "name": meta[0], "group": meta[1], "base": params[key]}
        for tg, fac in (("lo", 0.75), ("hi", 1.25)):
            p2 = dict(params)
            p2[key] = params[key] * fac
            vals = run_all(p2, needs, vecs, idx)
            d = [(v - b) / b for v, b in zip(vals, base)]
            rec[tg] = float(np.mean(d))
        rec["impact"] = max(abs(rec["lo"]), abs(rec["hi"]))
        rows.append(rec)
    rows.sort(key=lambda r: -r["impact"])

    # ---- 范数阶数 ----
    norm_scan = []
    for nn in (2.0, 2.5, 3.0, 4.0, 6.0, 10.0):
        p2 = dict(params); p2["NORM"] = nn
        vals = run_all(p2, needs, vecs, idx)
        norm_scan.append({"norm": nn,
                          "ratio": [v / b for v, b in zip(vals, base)],
                          "rank_rho": _spearman(base, vals)})

    # ---- 「最小总轮数」 vs 「最小总时间」 ----
    cmp_rows = []
    for i, nd in enumerate(needs):
        t_time, ks_time = solve(nd, vecs, idx, cost0, draws0, reset0, params["NORM"])
        unit = {sid: {z: nd[sid] / (draws0[z] * vecs[z][idx[sid]])
                      if vecs[z][idx[sid]] > 0 else float("inf") for z in ZONES} for sid in nd}
        acc = {z: 0.0 for z in ZONES}
        for sid in nd:
            b = max(ZONES, key=lambda z: vecs[z][idx[sid]])
            if vecs[b][idx[sid]] > 0:
                acc[b] += unit[sid][b] ** params["NORM"]
        ks_r = {z: acc[z] ** (1 / params["NORM"]) for z in ZONES}
        t_r = (sum(ks_r[z] * cost0[z] for z in ZONES)
               + max(ks_r["holy"], ks_r["fungi"]) * reset0)
        cmp_rows.append({"name": f"{recipes[i]['page']}/{recipes[i]['level']}",
                         "time_opt": t_time, "rounds_opt_time": t_r,
                         "rounds_holy": ks_r["holy"], "rounds_fungi": ks_r["fungi"],
                         "rounds_hell": ks_r["hell"],
                         "time_holy": ks_time["holy"], "time_fungi": ks_time["fungi"],
                         "time_hell": ks_time["hell"]})
    over = float(np.mean([r["rounds_opt_time"] / r["time_opt"] for r in cmp_rows]))

    # ---- 代表法术的单份成本 ----
    rep_rows = []
    for sid in REP:
        if sid not in idx:
            continue
        row = {"id": sid, "name": SPELL_CN.get(sid, sid)}
        for z in ZONES:
            pr = vecs[z][idx[sid]]
            row[z] = float(cost0[z] / (draws0[z] * pr)) if pr > 0 else None
        rep_rows.append(row)

    print("  S 基线：", " ".join("%.0f" % x for x in base))
    print("  前三敏感：", ", ".join("%s %+.0f%%" % (r["name"], r["impact"] * 100) for r in rows[:3]))
    print("  轮数最优 / 时间最优 = %.2f×" % over)
    return {"base": {k: params[k] for k in params},
            "derived": {"cost": cost0, "draws": draws0, "reset": reset0},
            "base_S": base, "rows": rows, "norm_scan": norm_scan,
            "rounds_vs_time": {"ratio": over, "rows": cmp_rows},
            "rep_spells": rep_rows}


def _spearman(a, b):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(o):
            r[i] = float(pos)
        return np.array(r)
    ra, rb = rank(a), rank(b)
    if ra.std() < 1e-12 or rb.std() < 1e-12:
        return 1.0
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    global SPELL_CN
    spells, vecs, idx, recipes, needs = load_all()
    SPELL_CN = {s["id"]: s.get("name_official") or s["id"]
                for s in json.load(open(S.WEIGHTS, encoding="utf-8"))["spells"]}

    d0 = analyse(BASE, needs, vecs, idx, recipes, "默认")
    d1 = analyse(EXPERT, needs, vecs, idx, recipes, "熟练")

    # 两种模式的单价对比
    modes = {}
    for tag, d in (("default", d0), ("expert", d1)):
        modes[tag] = {"cost": d["derived"]["cost"], "draws": d["derived"]["draws"],
                      "reset": d["derived"]["reset"],
                      "per_draw": {z: d["derived"]["cost"][z] / d["derived"]["draws"][z] for z in ZONES},
                      "base_S": d["base_S"],
                      "ratio_rounds": d["rounds_vs_time"]["ratio"]}
    print("\n每抽成本  默认 %.2f / %.2f / %.2f  熟练 %.2f / %.2f / %.2f"
          % (modes["default"]["per_draw"]["holy"], modes["default"]["per_draw"]["fungi"],
             modes["default"]["per_draw"]["hell"], modes["expert"]["per_draw"]["holy"],
             modes["expert"]["per_draw"]["fungi"], modes["expert"]["per_draw"]["hell"]))

    out = {"modes": modes, "default": d0, "expert": d1,
           "top_default": [r["name"] for r in d0["rows"][:5]],
           "top_expert": [r["name"] for r in d1["rows"][:5]]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n写入", OUT)


if __name__ == "__main__":
    main()
