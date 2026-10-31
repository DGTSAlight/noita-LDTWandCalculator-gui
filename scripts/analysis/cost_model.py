# -*- coding: utf-8 -*-
"""口径 v7.1：把「时间代价」按用户给的物理量算出来（提案阶段，未接入引擎）。

单位：1 = 直线穿过 1 个 chunk（512 px）**空隙地形**的时间。

用户给的参数（2026-10-30）：
  搜索 1 个区块的法杖 ≈ 在该环境内跑 4 个区块（绕区块一周）
  搜索 1 个区块的法术 ≈ 在该环境内跑 2 个区块
  地形：空隙 1.0 / 混合 2.0 / 固体 4.0（用户把 10 改成 4）
  繁茂内部是混合地形，但危险性 ×2
  圣山内部空隙、两层圣山之间混合、圣山底部回地面空隙（已打通）
  跨平行世界：70 chunk 空隙 + 3000 px 固体
  地狱重刷：22000 px 空隙
  主世界 7 座圣山已搜完 → 只算平行世界的 6 座

输出：每个渠道的「每份成本」与「每份抽取成本」，以及 51 个法术的最优渠道。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIONS = os.path.join(ROOT, "data", "parsed", "actions_full.json")
WEIGHTS = os.path.join(ROOT, "data", "spell_weights.json")

# ---- 地形 ----
VOID, MIXED, SOLID = 1.0, 2.0, 4.0
DANGER_FUNGI = 2.0          # 繁茂危险性惩罚

# ---- 搜索量（跑几个区块的距离 / 每搜索 1 个单位）----
RUN_PER_WAND_CHUNK = 4.0    # 法杖：绕区块一周
RUN_PER_SPELL_CHUNK = 2.0   # 法术：看卡就够

# ---- 区域参数 ----
HOLY_DRAWS = 16.2           # 每座圣山 5.05 卡 + 2.475 杖 × 4.5
HOLY_GAP_CHUNKS = 3.27      # 两层圣山之间的垂直距离
HELL_DENSITY = 0.73         # 张/chunk（A 模式走廊平均）
HELL_LOOP_CHUNKS = 86
HELL_LOOP_VOID = 22000 / 512   # 重刷一轮的空隙距离 = 43 chunk
# 繁茂：用户实测「仅上繁茂（42 chunk）就捡到 72 根法杖」（可能还数少了）
# → 1.714 根/chunk × 4.5 张/根 = 7.71 张卡/chunk（旧值 1.12 是按图集 14 个标记算的，低了 7 倍）
FUNGI_WANDS_PER_CHUNK = 72 / 42
FUNGI_DENSITY = FUNGI_WANDS_PER_CHUNK * 4.5   # 4.5 张/根，见 CARDS_PER_WAND
ASCEND_CHUNKS = 13110 / 512          # 最深圣山 → 地面（已打通，空隙）
WALL_CHUNKS = 3000 / 512             # 70 chunk 里含的固体墙
PARALLEL_HOP = ASCEND_CHUNKS * VOID + (70 - WALL_CHUNKS) * VOID + WALL_CHUNKS * SOLID  # ≈113.2

# ---- 各渠道「每个搜索单位」的总代价 ----
HOLY_COST_PER_SHRINE = RUN_PER_SPELL_CHUNK * VOID + HOLY_GAP_CHUNKS * MIXED
HELL_COST_PER_CHUNK = RUN_PER_SPELL_CHUNK * MIXED + HELL_LOOP_VOID / HELL_LOOP_CHUNKS * VOID
FUNGI_COST_PER_CHUNK = RUN_PER_WAND_CHUNK * MIXED * DANGER_FUNGI

# ---- 渠道的等级组合（精确等级）----
FUNGI_LEVELS = [2, 3, 4]
HOLY_SPELL_LEVELS = [0, 1, 2, 2, 3, 4]
HOLY_WAND_LEVELS = [0, 0, 1, 1, 2, 3]
HELL_LEVEL = 10
P_SPELL_SHOP = 51 / 101
CARDS_PER_WAND = 4.5


def load():
    data = json.load(open(ACTIONS, encoding="utf-8"))
    spells = {s["id"]: s for s in data["spells"]}
    for sp in spells.values():
        sp["tiers"] = {int(k): v for k, v in sp["tiers"].items()}
    tot_all = {int(k): v for k, v in data["tier_weight_all"].items()}
    tot_type = {int(t): {int(k): v for k, v in d.items()} for t, d in data["tier_weight_by_type"].items()}
    wiki = json.load(open(WEIGHTS, encoding="utf-8"))
    return spells, tot_all, tot_type, [s["id"] for s in wiki["spells"]]


def p_wand(sp, tot_type, m):
    if sp["type"] not in (0, 1, 2, 3):
        return 0.0
    w = sp["tiers"].get(m, 0.0)
    den = tot_type.get(sp["type"], {}).get(m, 0.0)
    return w / den if w and den else 0.0


def p_shop(sp, tot_all, m):
    w = sp["tiers"].get(m, 0.0)
    den = tot_all.get(m, 0.0)
    return w / den if w and den else 0.0


def main():
    spells, tot_all, tot_type, project = load()

    print(f"跨平行世界一跳 = {PARALLEL_HOP:.1f} 单位（上升 {ASCEND_CHUNKS:.1f} 空隙 + {70-WALL_CHUNKS:.1f} 空隙 + {WALL_CHUNKS:.2f} 固体×4）")
    holy_round = 6 * RUN_PER_SPELL_CHUNK * VOID + 5 * HOLY_GAP_CHUNKS * MIXED + (1500 / 512 * SOLID + 2000 / 512 * MIXED)
    print(f"圣山一轮（6 座 + 眼睛房间）= {holy_round:.1f} 单位，产出 97 次抽取 + 8 张卡")
    print(f"圣山 → 繁茂 = {4000/512*VOID + 1500/512*MIXED:.2f} 单位")
    print(f"圣山每座 = {HOLY_COST_PER_SHRINE:.2f} 单位（搜索 {RUN_PER_SPELL_CHUNK*VOID:.1f} + 层间 {HOLY_GAP_CHUNKS*MIXED:.2f}）")
    print(f"地狱每 chunk = {HELL_COST_PER_CHUNK:.2f} 单位")
    print(f"繁茂每 chunk = {FUNGI_COST_PER_CHUNK:.2f} 单位（4 × 混合2 × 危险2）")
    print()
    print("每份成本（单位/份）与每份抽取成本（单位/次抽取）：")
    print(f"  圣山：{HOLY_COST_PER_SHRINE/HOLY_DRAWS:8.3f} / 次抽取")
    print(f"  地狱：{HELL_COST_PER_CHUNK/HELL_DENSITY:8.3f} / 次抽取")
    print(f"  繁茂：{FUNGI_COST_PER_CHUNK/FUNGI_DENSITY:8.3f} / 次抽取")
    print()

    rows = []
    for sid in project:
        if sid not in spells:
            continue
        sp = spells[sid]
        p_f = sum(p_wand(sp, tot_type, m) for m in FUNGI_LEVELS) / len(FUNGI_LEVELS)
        p_h = (P_SPELL_SHOP * sum(p_shop(sp, tot_all, m) for m in HOLY_SPELL_LEVELS) / len(HOLY_SPELL_LEVELS)
               + (1 - P_SPELL_SHOP) * sum(p_wand(sp, tot_type, m) for m in HOLY_WAND_LEVELS) / len(HOLY_WAND_LEVELS))
        p_e = p_shop(sp, tot_all, HELL_LEVEL)

        y_h = HOLY_DRAWS * p_h                       # 份/座
        y_e = HELL_DENSITY * p_e                     # 份/chunk
        y_f = FUNGI_DENSITY * p_f                    # 份/chunk

        c_h = HOLY_COST_PER_SHRINE / y_h if y_h else float("inf")
        c_e = HELL_COST_PER_CHUNK / y_e if y_e else float("inf")
        c_f = FUNGI_COST_PER_CHUNK / y_f if y_f else float("inf")

        best = min([(c_h, "圣山"), (c_e, "地狱"), (c_f, "繁茂")])
        rows.append((best[0], sid, c_h, c_e, c_f, best[1], y_h, y_e, y_f))

    print(f"{'id':24s}{'圣山':>12s}{'地狱':>12s}{'繁茂':>12s}{'最优':>8s}{'渠道':>7s}")
    for c, sid, ch, ce, cf, z, yh, ye, yf in sorted(rows, reverse=True):
        fmt = lambda v: ("—" if v == float("inf") else f"{v:11.1f}")
        print(f"{sid:24s}{fmt(ch)}{fmt(ce)}{fmt(cf)}{c:12.1f}{z:>7s}")

    n = {"圣山": 0, "地狱": 0, "繁茂": 0}
    for r in rows:
        n[r[5]] += 1
    print("\n最优渠道分布：", n)


if __name__ == "__main__":
    main()
