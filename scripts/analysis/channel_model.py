# -*- coding: utf-8 -*-
"""口径 v4「三渠道 · 等效扫图」的计算与对比（提案阶段，未接入引擎）。

三个渠道（宝箱已按用户意见排除）：
  繁茂法杖   fungiforest 的 g_items：13.2 根/次，max_level 2/3/4 各 1/3，**按类型过滤**抽
  圣山商店   temple_altar：50.5% 法术店（10 张卡，max_level = 0/1/2/2/3/4）+ 49.5% 法杖店（5 根，max_level = 0/0/1/1/2/3）
  地狱商店   the_end 的 specialshop：6 张 10 级法术卡（全类型）

口径：
  p_G(s)  单次抽取命中率（v4 用源码分布算，不再用「模式内等级均匀」）
  Y_G(s)  单次扫图期望获得份数 = 抽取数 × p_G(s)
  cost    缺口 / Y_G(s)                该渠道需要的扫图次数
  S       Σ_G ( Σ_{s∈G} cost^3 )^(1/3)  指派：各自最有利作初值 + 最速下降

用法：
  python scripts/analysis/channel_model.py            # 打印三渠道命中率 + 单法术难度
  python scripts/analysis/channel_model.py all         # 51 个法术全部缺 1 份时的 S（v3 vs v4）
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIONS = os.path.join(ROOT, "data", "parsed", "actions_full.json")
WEIGHTS = os.path.join(ROOT, "data", "spell_weights.json")

# ---- 源码常量（第7次分析） ----
FUNGI_LEVELS = [2, 3, 4]                 # fungiforest: unshuffle_03/04 + level_05_better
HOLY_SPELL_LEVELS = [0, 1, 2, 2, 3, 4]   # 6 座圣山，法术店 level = biomeid
HOLY_WAND_LEVELS = [0, 0, 1, 1, 2, 3]    # 法杖店 level = clamp(biomeid,1,6) - 1
P_SPELL_SHOP = 51 / 101                  # Random(0,100) <= 50
HOLY_STALLS = 5
HOLY_CARD_ROWS = 2
HELL_LEVEL = 10

HOLY_CARD_DRAWS = HOLY_STALLS * HOLY_CARD_ROWS * P_SPELL_SHOP      # 5.05
HOLY_WAND_DRAWS = HOLY_STALLS * (1 - P_SPELL_SHOP)                 # 2.475

# ---- 单位：每 chunk（512×512）的期望抽取次数（2026-10-29 用户给的几何） ----
CARDS_PER_WAND = 4.5        # card_count = Random(0.51*cap, cap)，cap 均值 6
FUNGI_TILES = 54            # wang 图集块数（27 块 28x15 + 27 块 15x28）
FUNGI_MARKERS = 14          # #00ff00 标记数
FUNGI_P_ALTAR = 0.94        # spawn_items 里 r>0.06
FUNGI_CHUNKS = 42 + 11      # 上繁茂 42 + 下繁茂 11（用户实测），图集 54 块 ≈ 1 块 1 chunk
FUNGI_DRAWS = FUNGI_MARKERS / FUNGI_CHUNKS * FUNGI_P_ALTAR * CARDS_PER_WAND   # ≈1.12 张/chunk

# 地狱：wiki 说约 512 个商店点，但用户实测「垂直探索 2 个区块宽的一轮循环」能拿 50~60 张（只算容易找到的）。
# 更细的实测：每轮循环有 2~3 个「法术密集区」，每个 1~3 chunk，密集区内每 chunk 10~15 张。
HELL_ZONES = 2.5            # (2+3)/2
HELL_CHUNKS_PER_ZONE = 2.0  # (1+3)/2
HELL_CARDS_PER_ZONE_CHUNK = 12.5   # (10+15)/2
HELL_LOOP_CARDS = HELL_ZONES * HELL_CHUNKS_PER_ZONE * HELL_CARDS_PER_ZONE_CHUNK   # ≈62.5 张/轮
HELL_LOOP_CHUNKS = 22000 / 512 * 2                                               # 43 chunk 高 × 2 宽 = 86
HELL_DRAWS = HELL_LOOP_CARDS / HELL_LOOP_CHUNKS                              # ≈0.73 张/chunk

HOLY_SPAN = 13110 - 1380    # 一层圣山到七层圣山的垂直距离
HOLY_CHUNKS = HOLY_SPAN / 512 / 7                                            # ≈3.27 chunk/座
HOLY_DRAWS = (HOLY_CARD_DRAWS + HOLY_WAND_DRAWS * CARDS_PER_WAND) / HOLY_CHUNKS  # ≈4.95 次/chunk

# 眼睛房间：8 张免费法术卡，从全部已解锁法术里均匀抽（无视等级权重）
EYE_CARDS = 8
EYE_PER_RUN = 7              # 假设每层圣山路上 1 间
EYE_DRAWS = EYE_CARDS * EYE_PER_RUN / (HOLY_CHUNKS * 7)                       # 张/chunk

# v3 现行口径（对比用）
V3_MODES = {
    "繁茂": {"levels": [2, 3, 4], "E": 2.00},
    "地狱": {"levels": [10], "E": 3.00},
    "均匀": {"levels": list(range(11)), "E": 1.45},
}


def load():
    data = json.load(open(ACTIONS, encoding="utf-8"))
    spells = {s["id"]: s for s in data["spells"]}
    for sp in spells.values():                     # JSON 的键是字符串，统一转 int
        sp["tiers"] = {int(k): v for k, v in sp["tiers"].items()}
    tot_all = {int(k): v for k, v in data["tier_weight_all"].items()}
    tot_type = {
        int(ty): {int(k): v for k, v in d.items()}
        for ty, d in data["tier_weight_by_type"].items()
    }
    wiki = json.load(open(WEIGHTS, encoding="utf-8"))
    project = [s["id"] for s in wiki["spells"]]
    pct = {s["id"]: {int(k): v for k, v in s["tiers_pct"].items()} for s in wiki["spells"]}
    return spells, tot_all, tot_type, project, pct


def cum(d, m):
    return sum(v for k, v in d.items() if k <= m)


def p_wand(spell, tot_type, m):
    """法杖渠道：**精确等级 m**（不是 0~m），先按类型过滤"""
    if spell["type"] not in (0, 1, 2, 3):
        return 0.0
    w = spell["tiers"].get(m, 0.0)
    den = tot_type.get(spell["type"], {}).get(m, 0.0)
    return w / den if (w > 0 and den > 0) else 0.0


def p_shop(spell, tot_all, m):
    """商店渠道：**精确等级 m**，全类型混抽"""
    w = spell["tiers"].get(m, 0.0)
    den = tot_all.get(m, 0.0)
    return w / den if (w > 0 and den > 0) else 0.0


def channel_rates(spell, tot_all, tot_type):
    """返回 {渠道: (单次抽取命中率, 单次扫图期望份数)}"""
    p_f = sum(p_wand(spell, tot_type, m) for m in FUNGI_LEVELS) / len(FUNGI_LEVELS)
    p_h = P_SPELL_SHOP * sum(p_shop(spell, tot_all, m) for m in HOLY_SPELL_LEVELS) / len(HOLY_SPELL_LEVELS) \
        + (1 - P_SPELL_SHOP) * sum(p_wand(spell, tot_type, m) for m in HOLY_WAND_LEVELS) / len(HOLY_WAND_LEVELS)
    p_e = p_shop(spell, tot_all, HELL_LEVEL)
    return {
        "繁茂": (p_f, p_f * FUNGI_DRAWS),
        "圣山": (p_h, p_h * (HOLY_CARD_DRAWS + HOLY_WAND_DRAWS)),
        "地狱": (p_e, p_e * HELL_DRAWS),
    }


def solve_v4(needs, rates, t=None):
    """needs: {id: 缺口}; rates: {id: {渠道: (p, Y)}}; t: 各渠道相对时间（默认 1）"""
    t = t or {"繁茂": 1.0, "圣山": 1.0, "地狱": 1.0}
    ids = list(needs)
    zones = ["繁茂", "圣山", "地狱"]

    def cost(sid, z):
        y = rates[sid][z][1] / t[z]
        return needs[sid] / y if y > 0 else float("inf")

    def total(assign):
        acc = 0.0
        for z in zones:
            cs = [cost(s, z) for s in ids if assign[s] == z]
            if cs:
                acc += sum(c ** 3 for c in cs) ** (1 / 3)
        return acc

    # 初值：各自最有利
    assign = {}
    for s in ids:
        best, bz = float("inf"), None
        for z in zones:
            c = cost(s, z)
            if c < best:
                best, bz = c, z
        assign[s] = bz if bz is not None else "无渠道"
    cur = total(assign)
    improved = True
    while improved:
        improved = False
        for s in ids:
            for z in zones:
                if z == assign[s] or cost(s, z) == float("inf"):
                    continue
                old = assign[s]
                assign[s] = z
                new = total(assign)
                if new < cur - 1e-9:
                    cur, improved = new, True
                else:
                    assign[s] = old
    return cur, assign


def solve_v3(needs, pct):
    """v3 现行口径：模式内等级均匀 + Wiki 百分比当命中率 + 经验倍率 E_G"""
    ids = list(needs)
    modes = list(V3_MODES)

    def gain(sid, z):
        cfg = V3_MODES[z]
        p = sum(pct.get(sid, {}).get(t, 0.0) for t in cfg["levels"]) / len(cfg["levels"]) / 100.0
        return p * cfg["E"]

    def cost(sid, z):
        g = gain(sid, z)
        return needs[sid] / g if g > 0 else float("inf")

    def total(assign):
        acc = 0.0
        for z in modes:
            cs = [cost(s, z) for s in ids if assign[s] == z]
            if cs:
                acc += sum(c ** 3 for c in cs) ** (1 / 3)
        return acc

    assign = {}
    for s in ids:
        best, bz = float("inf"), None
        for z in modes:
            c = cost(s, z)
            if c < best:
                best, bz = c, z
        assign[s] = bz
    cur = total(assign)
    improved = True
    while improved:
        improved = False
        for s in ids:
            for z in modes:
                if z == assign[s] or cost(s, z) == float("inf"):
                    continue
                old = assign[s]
                assign[s] = z
                new = total(assign)
                if new < cur - 1e-9:
                    cur, improved = new, True
                else:
                    assign[s] = old
    return cur, assign


def main():
    spells, tot_all, tot_type, project, pct = load()
    rates = {s: channel_rates(spells[s], tot_all, tot_type) for s in project if s in spells}

    print(f"每 chunk 的期望抽取数：繁茂 {FUNGI_DRAWS:.2f} 张卡 / 圣山 {HOLY_DRAWS:.2f} 次"
          f"（每座 {HOLY_CARD_DRAWS + HOLY_WAND_DRAWS * CARDS_PER_WAND:.1f} 次，折 {HOLY_CHUNKS:.2f} chunk）"
          f" / 地狱 {HELL_DRAWS:.2f} 张（{HELL_LOOP_CARDS:.1f} 张 ÷ {HELL_LOOP_CHUNKS:.0f} chunk）")

    if len(sys.argv) > 1 and sys.argv[1] == "all":
        needs = {s: 1 for s in rates}
        s4, a4 = solve_v4(needs, rates)
        s3, a3 = solve_v3(needs, pct)
        print(f"\n全部 51 个法术各缺 1 份：v3 S = {s3:.1f}（等效抽取）  v6 S = {s4:.1f}（chunk）")
        for z in ["繁茂", "圣山", "地狱", "均匀"]:
            n4 = sum(1 for s in a4 if a4[s] == z)
            n3 = sum(1 for s in a3 if a3[s] == z)
            if n4 or n3:
                print(f"   {z}: v6 指派 {n4} 个 / v3 指派 {n3} 个")
        return

    print(f"\n{'id':24s}{'类型':>4s}{'繁茂p':>9s}{'繁茂Y':>9s}{'圣山p':>9s}{'圣山Y':>9s}{'地狱p':>9s}{'地狱Y':>9s}"
          f"{'v5 chunk':>10s}{'v3抽数':>9s}{'渠道':>7s}")
    rows = []
    for s in project:
        if s not in rates:
            continue
        r = rates[s]
        s4, a4 = solve_v4({s: 1}, rates)
        s3, _ = solve_v3({s: 1}, pct)
        rows.append((s4, s, r, s3, a4[s]))
    for s4, s, r, s3, z in sorted(rows, key=lambda x: (-x[0], x[1])):
        print(f"{s:24s}{spells[s]['type']:>4d}"
              f"{100*r['繁茂'][0]:>9.3f}{r['繁茂'][1]:>9.4f}"
              f"{100*r['圣山'][0]:>9.3f}{r['圣山'][1]:>9.4f}"
              f"{100*r['地狱'][0]:>9.3f}{r['地狱'][1]:>9.4f}"
              f"{s4:>10.1f}{s3:>9.1f}{z:>7s}")

    out = {
        "note": "口径 v5 的三渠道命中率（p=单次抽取命中率, Y=每 chunk 期望份数）",
        "draws_per_chunk": {"繁茂": FUNGI_DRAWS, "圣山": HOLY_DRAWS, "地狱": HELL_DRAWS},
        "spells": {
            s: {
                "type": spells[s]["type"],
                "p": {z: rates[s][z][0] for z in rates[s]},
                "Y": {z: rates[s][z][1] for z in rates[s]},
            }
            for s in rates
        },
    }
    dst = os.path.join(ROOT, "data", "parsed", "channel_rates.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {os.path.relpath(dst, ROOT)}")


if __name__ == "__main__":
    main()
