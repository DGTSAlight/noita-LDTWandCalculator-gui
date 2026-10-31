# -*- coding: utf-8 -*-
"""时间代价模型内部四个方案的口径对比（2026-10-31）。

单位：1 = 直线穿过 1 个 chunk（512 px）空隙地形的时间。

四个方案（都属「时间代价模型」，区别只在常数与库存规则）：

  S1  v7 经验系数版
      搜索系数是拍出来的：圣山 0.4/座、地狱 0.7/chunk、繁茂 1.0/chunk；
      固体地形系数 10；不建模库存（等于假设商店无限）。

  S2  v7.1 物理量版
      换成用户给的物理量：搜 1 个区块的法杖 ≈ 在该环境跑 4 个区块、法术 ≈ 跑 2 个区块；
      固体地形系数改为 4；补上眼睛房间（19.5）与繁茂入场（13.67）；仍不建模库存。

  S3  v7.2 按轮版
      不再「每 chunk 摊一点」，改成「走一轮一次性付」；跨平行世界 113.2 单独计价，
      但只在「第二轮起」才付，且圣山与繁茂分别计。

  S4  v7.2 修正版（现行）
      主世界 7 座圣山已搜完 → 第一轮就要跨世界；一趟平行世界同时补满圣山与繁茂，
      所以开世界次数 = max(k_圣山, k_繁茂)；按法术分配（不是按整组缺口）。

指标：
  比值   = 仿真时间 ÷ 口径值，理想 1.00
   仿真时间：sim_v7.py 的 greedy 策略，2000 次/配方，取中位数
   口径值  ：本脚本按各方案算出的 S
  变异系数 = 比值的标准差 ÷ 均值，越小说明这把尺子越稳定
  Spearman = 口径排序与仿真排序的秩相关，1.00 表示排序完全一致

用法：python scripts/analysis/compare_v7.py [runs]
输出：data/parsed/scheme_compare.json 与 docs/charts/*.png
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_v7 as S  # noqa: E402

ROOT = S.ROOT
OUT_JSON = os.path.join(ROOT, "data", "parsed", "scheme_compare.json")
CHART_DIR = os.path.join(ROOT, "docs", "charts")

ZONES = ("holy", "fungi", "hell")
ZONE_CN = {"holy": "圣山", "fungi": "繁茂", "hell": "地狱"}

# 跨平行世界：上升 25.6 空隙 + 64.1 空隙 + 5.86 chunk 固体×4
WORLD_RESET = S.WORLD_RESET

# ---- 各方案的单轮成本与产出 ----------------------------------------------
# draws 是「走一轮能抽几次」，各方案只有圣山因为眼睛房间的有无而不同
DRAWS = {
    "S1": {"holy": 6 * 16.19, "fungi": 324.0, "hell": 62.0},   # v7 没算眼睛房间
    "S2": {"holy": S.HOLY_DRAWS, "fungi": 324.0, "hell": 62.0},
    "S3": {"holy": S.HOLY_DRAWS, "fungi": 324.0, "hell": 62.0},
    "S4": {"holy": S.HOLY_DRAWS, "fungi": 324.0, "hell": 62.0},
}

COST = {
    # 6 座 × 8.54（搜索 2×空隙1.0 + 层间 3.27×混合2.0）；繁茂 42×16.0；地狱 86×4.50
    "S1": {"holy": 6 * 8.54, "fungi": 42 * 16.0, "hell": 86 * 4.50},
    # 加眼睛房间 19.5、繁茂入场 13.67
    "S2": {"holy": 6 * 8.54 + 19.5, "fungi": 42 * 16.0 + 13.67, "hell": 86 * 4.50},
    # 按轮：圣山 6×(层间 6.54 + 搜索 2.99) + 眼睛 19.5
    "S3": {"holy": 76.7, "fungi": 685.67, "hell": 387.0},
    "S4": {"holy": 76.7, "fungi": 685.67, "hell": 387.0},
}

# 换世界规则
#   none  : 不建模库存
#   per   : 各区域分别付，且只在第二轮起（max(0, k-1)）
#   share : 圣山与繁茂共享一次跳世界，第一轮就付（max(k_holy, k_fungi)）
HOP = {"S1": "none", "S2": "none", "S3": "per", "S4": "share"}

LABEL = {
    "S1": "v7 经验系数",
    "S2": "v7.1 物理量",
    "S3": "v7.2 按轮",
    "S4": "v7.2 修正（现行）",
}


def hop_cost(ks, mode):
    """ks = {zone: 轮数}；返回需要额外付出的换世界时间。"""
    if mode == "none":
        return 0.0
    world = [ks["holy"], ks["fungi"]]
    if mode == "per":
        return sum(max(0.0, k - 1.0) for k in world) * WORLD_RESET
    return max(world) * WORLD_RESET


def solve(need, vecs, idx, scheme):
    """按某个方案算一组缺口的 S。

    need : {spell_id: 缺口份数}
    vecs : sim_v7.build_vectors 的产物，vecs[zone] 是各法术的单次命中概率向量
    idx  : spell_id -> 在向量里的下标
    scheme: "S1".."S4"

    返回 dict：total（S 值）、rounds（各区域轮数）、stage（各区域时间）
    """
    ids = [s for s in need if s in idx]
    if not ids:
        return {"total": 0.0, "rounds": {z: 0.0 for z in ZONES},
                "stage": {z: 0.0 for z in ZONES}}

    draws, cost = DRAWS[scheme], COST[scheme]
    n = len(ids)
    # cost[i][z] = 这个法术在第 z 区「一个人刷完」要几轮
    unit = []
    for sid in ids:
        row = {}
        for z in ZONES:
            p = vecs[z][idx[sid]]
            row[z] = need[sid] / (draws[z] * p) if p > 0 else float("inf")
        unit.append(row)

    # 初值：每个法术去自己最便宜的区域
    assign = []
    acc = {z: 0.0 for z in ZONES}
    for i in range(n):
        best = min(ZONES, key=lambda z: unit[i][z])
        assign.append(best)
        if np.isfinite(unit[i][best]):
            acc[best] += unit[i][best] ** 3

    def total_of(acc_now):
        ks = {z: acc_now[z] ** (1.0 / 3.0) for z in ZONES}
        t = sum(ks[z] * cost[z] for z in ZONES) + hop_cost(ks, HOP[scheme])
        return t, ks

    cur, _ = total_of(acc)

    # 最速下降：反复尝试把某个法术挪到别的区域，只要总 S 下降就接受
    for _ in range(30):
        best_delta, move = -1e-9, None
        for i in range(n):
            frm = assign[i]
            for z in ZONES:
                if z == frm or not np.isfinite(unit[i][z]):
                    continue
                old_f, old_z = acc[frm], acc[z]
                acc[frm] = max(0.0, old_f - (unit[i][frm] ** 3 if np.isfinite(unit[i][frm]) else 0.0))
                acc[z] = old_z + unit[i][z] ** 3
                t, _ = total_of(acc)
                acc[frm], acc[z] = old_f, old_z
                if t - cur < best_delta:
                    best_delta, move = t - cur, (i, z)
        if move is None:
            break
        i, z = move
        frm = assign[i]
        if np.isfinite(unit[i][frm]):
            acc[frm] = max(0.0, acc[frm] - unit[i][frm] ** 3)
        acc[z] += unit[i][z] ** 3
        assign[i] = z
        cur, _ = total_of(acc)

    total, ks = total_of(acc)
    hop = hop_cost(ks, HOP[scheme])
    # 把共享的换世界成本按轮数比例摊给圣山/繁茂，便于画图
    stage = {}
    world_k = ks["holy"] + ks["fungi"]
    for z in ZONES:
        share = 0.0
        if z != "hell" and world_k > 0:
            share = hop * ks[z] / world_k
        stage[z] = ks[z] * cost[z] + share
    return {"total": total, "rounds": ks, "stage": stage}


def spearman(a, b):
    """秩相关：先把两组数各自换成名次，再算皮尔逊相关系数。取值 -1~1。"""
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and abs(v[order[j + 1]] - v[order[i]]) < 1e-12:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return np.array(r)

    ra, rb = rank(a), rank(b)
    if ra.std() < 1e-12 or rb.std() < 1e-12:
        return 1.0
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    spells, tot_all, tot_type, project = S.load()
    vecs, idx = S.build_vectors(spells, tot_all, tot_type, project)
    recipes = json.load(open(S.RECIPES, encoding="utf-8"))

    # ---- 仿真真值（greedy 策略）----
    rng = np.random.default_rng(20261031)
    truth = {"default": [], "expert": []}
    for mode in ("default", "expert"):
        for r in recipes:
            vals = [S.simulate(r, vecs, idx, None, rng, "greedy", run_mode=mode)[0]
                    for _ in range(runs)]
            truth[mode].append(float(np.median(vals)))

    # ---- 各方案的 S ----
    schemes = ["S1", "S2", "S3", "S4"]
    table = {}
    for sch in schemes:
        rows = []
        for r in recipes:
            need = {it["id"]: it["lack"] for it in r["need"] if it["id"] in idx}
            rows.append(solve(need, vecs, idx, sch))
        table[sch] = rows

    names = [f"{r['page']}/{r['level']}" for r in recipes]
    report = {"runs": runs, "names": names, "truth": truth,
              "schemes": {}, "label": LABEL}

    print(f"仿真真值（{runs} 次/配方，greedy，默认模式）")
    for nm, t in zip(names, truth["default"]):
        print(f"  {nm:22s} {t:8.0f}")

    print(f"\n{'方案':22s}{'比值范围':>16s}{'中位':>8s}{'变异系数':>10s}{'最大偏差':>10s}{'全局ρ':>8s}")
    for sch in schemes:
        S_vals = [row["total"] for row in table[sch]]
        ratio = [t / s if s > 0 else float("nan") for t, s in zip(truth["default"], S_vals)]
        arr = np.array([x for x in ratio if np.isfinite(x)])
        cv = float(arr.std() / arr.mean())
        rho_all = spearman(S_vals, truth["default"])
        # 页内：9 个配方按 3 页各 3 条切
        rho_pages = [spearman(S_vals[i * 3:(i + 1) * 3], truth["default"][i * 3:(i + 1) * 3])
                     for i in range(3)]
        report["schemes"][sch] = {
            "label": LABEL[sch],
            "S": S_vals,
            "ratio": ratio,
            "cv": cv,
            "maxdev": float(np.max(np.abs(arr - 1.0))),
            "rho_all": rho_all,
            "rho_pages": rho_pages,
            "rounds": [{z: row["rounds"][z] for z in ZONES} for row in table[sch]],
            "stage": [{z: row["stage"][z] for z in ZONES} for row in table[sch]],
        }
        print(f"{LABEL[sch]:22s}{min(arr):6.2f} ~ {max(arr):6.2f}"
              f"{np.median(arr):8.2f}{cv:10.3f}{np.max(np.abs(arr-1.0)):10.3f}{rho_all:8.3f}")

    # ---- 熟练模式下的现行方案 ----
    print(f"\n现行方案两种模式")
    # 熟练：繁茂 517.67、地狱 97（其余同 S4）
    COST["S4X"] = {"holy": 76.7, "fungi": 517.67, "hell": 97.0}
    DRAWS["S4X"] = DRAWS["S4"]
    HOP["S4X"] = "share"
    exp_rows = []
    for r in recipes:
        need = {it["id"]: it["lack"] for it in r["need"] if it["id"] in idx}
        exp_rows.append(solve(need, vecs, idx, "S4X"))
    ratio_e = [t / s for t, s in zip(truth["expert"], [x["total"] for x in exp_rows])]
    arr_e = np.array(ratio_e)
    report["expert"] = {
        "S": [x["total"] for x in exp_rows],
        "ratio": ratio_e,
        "cv": float(arr_e.std() / arr_e.mean()),
        "rho_all": spearman([x["total"] for x in exp_rows], truth["expert"]),
        "truth": truth["expert"],
    }
    print(f"  熟练 比值 {min(arr_e):.2f}~{max(arr_e):.2f} 中位 {np.median(arr_e):.2f}"
          f" 变异 {arr_e.std()/arr_e.mean():.3f} ρ={report['expert']['rho_all']:.3f}")

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(report, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n写入 {OUT_JSON}")
    return report


if __name__ == "__main__":
    main()
