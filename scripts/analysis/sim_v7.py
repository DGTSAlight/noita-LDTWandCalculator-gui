# -*- coding: utf-8 -*-
"""口径 v7.2 的策略仿真：按真实配方跑蒙特卡洛，比较四种搜索策略。

单位：1 = 直线穿过 1 个 chunk（512 px）空隙地形的时间。

区域（全部来自 docs/权重口径评估.md §11~§12）：
  圣山   一轮 = 6 座（层 0/1/2/2/3/4，每座 50.5% 法术店 / 49.5% 法杖店）+ 1 眼睛房间
         每座 = 层间行进 3.27×混合2.0 + 搜索（法术店 2×空隙、法杖店 4×空隙）
  繁茂   只搜上块 42 chunk，密度 7.71 张卡/chunk，内部 4×混合2×危险2 = 16/chunk
  地狱   一轮 86 chunk（2 chunk 宽 × 43 高），密度 0.73 张卡/chunk，内部 2×混合2 + 43/86
库存：圣山/繁茂 一轮后要跨平行世界 113.2 才有新的；地狱自带 43 的重刷成本（已摊进 4.5/chunk）。

用法：python scripts/analysis/sim_v7.py [runs] [default|expert]
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIONS = os.path.join(ROOT, "data", "parsed", "actions_full.json")
RECIPES = os.path.join(ROOT, "data", "parsed", "recipes.json")
WEIGHTS = os.path.join(ROOT, "data", "spell_weights.json")

VOID, MIXED, SOLID = 1.0, 2.0, 4.0
# 繁茂危险惩罚：默认 2.0；熟练玩家 1.5（2026-10-31 用户定）
DANGER_FUNGI = {"default": 2.0, "expert": 1.5}
RUN_PER_WAND_CHUNK, RUN_PER_SPELL_CHUNK = 4.0, 2.0

HOLY_GAP = 3.27
HOLY_SPELL_LEVELS = [0, 1, 2, 2, 3, 4]
HOLY_WAND_LEVELS = [0, 0, 1, 1, 2, 3]
P_SPELL_SHOP = 51 / 101
EYE_CARDS = 8
EYE_COST = 1500 / 512 * SOLID + 2000 / 512 * MIXED
HOLY_SESSION_COST = 6 * HOLY_GAP * MIXED + 6 * (P_SPELL_SHOP * RUN_PER_SPELL_CHUNK * VOID
                                                 + (1 - P_SPELL_SHOP) * RUN_PER_WAND_CHUNK * VOID) + EYE_COST

FUNGI_CHUNKS = 42
FUNGI_ENTRY = 4000 / 512 * VOID + 1500 / 512 * MIXED
FUNGI_DENSITY = (72 / FUNGI_CHUNKS) * 4.5


def fungi_cost(mode="default"):
    return FUNGI_CHUNKS * RUN_PER_WAND_CHUNK * MIXED * DANGER_FUNGI[mode] + FUNGI_ENTRY

# 地狱：产出恒定 62.5 张/轮，两种模式只差「要走多少区块」
HELL_CHUNKS = {"default": 86, "expert": 10}    # 默认扫整轮走廊 / 熟练只搜密集区附近
HELL_TRAVERSE = {"default": 0, "expert": 14}   # 熟练：两侧穿行 7000 px ≈ 14 chunk 空隙
HELL_CHUNK_COST = RUN_PER_SPELL_CHUNK * MIXED  # 搜 1 chunk 法术 = 跑 2 chunk × 混合 2.0
HELL_REFILL = 43                               # 补货难度不变
HELL_CARDS = 62.5
HELL_DENSITY = HELL_CARDS / HELL_CHUNKS["default"]


def hell_cost(mode="default"):
    return (HELL_CHUNKS[mode] * HELL_CHUNK_COST
            + HELL_TRAVERSE[mode] * VOID
            + HELL_REFILL)

WORLD_RESET = 13110 / 512 * VOID + (70 - 3000 / 512) * VOID + (3000 / 512) * SOLID
CARDS_PER_WAND = 4.5
EYE_POOL = 465
# 圣山一轮的真实抽取数：6 座 × (50.5% 法术店 10 张 + 49.5% 法杖店 5 根×4.5) + 眼睛 8 张 ≈ 105
HOLY_DRAWS = 6 * (P_SPELL_SHOP * 10 + (1 - P_SPELL_SHOP) * 5 * CARDS_PER_WAND) + EYE_CARDS


def load():
    data = json.load(open(ACTIONS, encoding="utf-8"))
    spells = {s["id"]: s for s in data["spells"]}
    for sp in spells.values():
        sp["tiers"] = {int(k): v for k, v in sp["tiers"].items()}
    tot_all = {int(k): v for k, v in data["tier_weight_all"].items()}
    tot_type = {int(t): {int(k): v for k, v in d.items()} for t, d in data["tier_weight_by_type"].items()}
    project = [s["id"] for s in json.load(open(WEIGHTS, encoding="utf-8"))["spells"]]
    project = [s for s in project if s in spells]
    return spells, tot_all, tot_type, project


def p_shop(sp, tot_all, m):
    w = sp["tiers"].get(m, 0.0)
    den = tot_all.get(m, 0.0)
    return w / den if w and den else 0.0


def p_wand(sp, tot_type, m):
    if sp["type"] not in (0, 1, 2, 3):
        return 0.0
    w = sp["tiers"].get(m, 0.0)
    den = tot_type.get(sp["type"], {}).get(m, 0.0)
    return w / den if w and den else 0.0


def build_vectors(spells, tot_all, tot_type, project):
    """各「抽卡源」在 51 个法术上的概率向量（最后一维 = 其它法术）。"""
    n = len(project)
    idx = {s: i for i, s in enumerate(project)}

    def pack(fn, m):
        v = np.zeros(n + 1)
        for s in project:
            v[idx[s]] = fn(spells[s], m)
        v[n] = max(0.0, 1.0 - v[:n].sum())
        return v

    holy_spell = [pack(lambda sp, mm: p_shop(sp, tot_all, mm), m) for m in HOLY_SPELL_LEVELS]
    holy_wand = [pack(lambda sp, mm: p_wand(sp, tot_type, mm), m) for m in HOLY_WAND_LEVELS]
    fungi = (pack(lambda sp, mm: p_wand(sp, tot_type, mm), 2)
             + pack(lambda sp, mm: p_wand(sp, tot_type, mm), 3)
             + pack(lambda sp, mm: p_wand(sp, tot_type, mm), 4)) / 3
    hell = pack(lambda sp, mm: p_shop(sp, tot_all, mm), 10)
    eye = np.array([1.0 / EYE_POOL] * n + [1 - n / EYE_POOL])

    holy_avg = (np.mean(holy_spell, axis=0) * P_SPELL_SHOP * 10
                + np.mean(holy_wand, axis=0) * (1 - P_SPELL_SHOP) * 5 * CARDS_PER_WAND
                + eye * EYE_CARDS)
    holy_avg = holy_avg / holy_avg.sum()
    return {"holy_spell": holy_spell, "holy_wand": holy_wand,
            "fungi": fungi, "hell": hell, "eye": eye, "holy": holy_avg}, idx


def run_session(zone, vecs, rng, gap, run_mode="default"):
    """跑一个 session，返回 (消耗时间, 各法术获得的份数向量)。"""
    n = len(gap)
    got = np.zeros(n, dtype=int)
    if zone == "holy":
        for k in range(6):
            if rng.random() < P_SPELL_SHOP:
                cnt = rng.multinomial(10, vecs["holy_spell"][k])
            else:
                cnt = rng.multinomial(int(round(5 * CARDS_PER_WAND)), vecs["holy_wand"][k])
            got += cnt[:n]
        got += rng.multinomial(EYE_CARDS, vecs["eye"])[:n]
        return HOLY_SESSION_COST, got
    if zone == "fungi":
        d = int(round(FUNGI_CHUNKS * FUNGI_DENSITY))
        return fungi_cost(run_mode), rng.multinomial(d, vecs["fungi"])[:n]
    d = int(round(HELL_CARDS))
    return hell_cost(run_mode), rng.multinomial(d, vecs["hell"])[:n]


def simulate(recipe, vecs, idx, order, rng, mode="priority", max_sessions=300, run_mode="default"):
    """跑一个配方。

    世界模型（2026-10-31 修正）：
      · 主世界 7 座圣山视为已搜完 → **第一轮就要跨平行世界**，所以开局 stock=0，
        第一次进圣山/繁茂都要先付 WORLD_RESET；
      · 跨到新世界会把圣山和繁茂**一起**补满（同一趟平行世界），所以跳世界时两者都重置；
      · 地狱可再生，重刷成本 43 已摊进单轮 4.5/chunk。
    """
    n = len(idx)
    gap = np.zeros(n, dtype=int)
    for it in recipe["need"]:
        if it["id"] in idx:
            gap[idx[it["id"]]] = it["lack"]

    sess_cost = {"holy": HOLY_SESSION_COST, "fungi": fungi_cost(run_mode), "hell": hell_cost(run_mode)}
    draws = {"holy": HOLY_DRAWS, "fungi": int(round(FUNGI_CHUNKS * FUNGI_DENSITY)),
             "hell": int(round(HELL_CARDS))}
    pvec = {"holy": vecs["holy"], "fungi": vecs["fungi"], "hell": vecs["hell"]}

    total = 0.0
    ptr = 0
    used = {"holy": 0, "fungi": 0, "hell": 0}
    by_zone = {"holy": np.zeros(n), "fungi": np.zeros(n), "hell": np.zeros(n)}
    stock = {"holy": 0, "fungi": 0, "hell": 10 ** 9}   # 0 = 本世界还没来过

    def enter(z):
        """进入区域 z：若本世界已搜过就跳一次世界（圣山+繁茂一起补满）"""
        nonlocal total
        if z == "hell":
            return
        if stock[z] <= 0:
            total += WORLD_RESET
            stock["holy"] = 1
            stock["fungi"] = 1

    for _ in range(max_sessions):
        if not gap.any():
            break
        if mode == "greedy":
            best, bz = -1.0, None
            for z in ("holy", "fungi", "hell"):
                p = pvec[z][:n]
                exp = np.minimum(gap, draws[z] * p).sum()
                c = sess_cost[z] + (WORLD_RESET if z != "hell" and stock[z] <= 0 else 0)
                if exp > 0 and exp / c > best:
                    best, bz = exp / c, z
            if bz is None:
                break
        else:
            # 轮转：每步取顺序里的下一个区域（跳过已经无法贡献的）
            bz = None
            for k in range(len(order)):
                cand = order[(ptr + k) % len(order)]
                if np.minimum(gap, draws[cand] * pvec[cand][:n]).sum() > 0:
                    bz = cand
                    ptr = (ptr + k + 1) % len(order)
                    break
            if bz is None:
                break
        enter(bz)
        stock[bz] -= 1
        c, got = run_session(bz, vecs, rng, gap, run_mode)
        total += c
        got = np.minimum(got, gap)          # 只记真正需要的份数
        by_zone[bz] += got
        gap = np.maximum(0, gap - got)
        used[bz] += 1
    return total, used, int(gap.sum()), by_zone


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    run_mode = sys.argv[2] if len(sys.argv) > 2 else "default"
    spells, tot_all, tot_type, project = load()
    vecs, idx = build_vectors(spells, tot_all, tot_type, project)
    recipes = json.load(open(RECIPES, encoding="utf-8"))

    print(f"[{run_mode}] 圣山一轮 {HOLY_SESSION_COST:.1f} / 繁茂一轮 {fungi_cost(run_mode):.1f}"
          f"（含入场 {FUNGI_ENTRY:.2f}，危险×{DANGER_FUNGI[run_mode]}）"
          f" / 地狱一轮 {hell_cost(run_mode):.1f}（搜索 {HELL_CHUNKS[run_mode]} chunk 混合 + {HELL_TRAVERSE[run_mode]} chunk 空隙 + 补货 {HELL_REFILL}）"
          f" / 换世界 {WORLD_RESET:.1f}")
    print(f"每轮抽取：圣山 约 {HOLY_DRAWS:.0f}（6 座：法术店 10 张 / 法杖店 {int(round(5*CARDS_PER_WAND))} 张，+ 眼睛 8）"
          f"；繁茂 {int(round(FUNGI_CHUNKS*FUNGI_DENSITY))}；地狱 {int(round(HELL_CARDS))}")
    print()

    strats = {
        "holy_first": (["holy", "fungi", "hell"], "priority"),
        "fungi_first": (["fungi", "holy", "hell"], "priority"),
        "hell_first": (["hell", "holy", "fungi"], "priority"),
        "greedy": (None, "greedy"),
    }
    rng = np.random.default_rng(20261031)
    print(f"{'配方':22s}{'holy':>9s}{'fungi':>9s}{'hell':>9s}{'greedy':>9s}   最优")
    wins = {k: 0 for k in strats}
    for r in recipes:
        name = f"{r['page']}/{r['level']}"
        row = {}
        for k, (order, mode) in strats.items():
            vals = [simulate(r, vecs, idx, order, rng, mode, run_mode=run_mode)[0] for _ in range(runs)]
            row[k] = float(np.median(vals))
        best = min(row, key=row.get)
        wins[best] += 1
        print(f"{name:22s}" + "".join(f"{row[k]:9.0f}" for k in strats) + f"   {best}")
    print("\n各策略胜场：", wins)

    # ---- 来源验证：每个法术实际是从哪个区域拿到的 ----
    print("\n=== 来源分布（按主等级分组，hell_first 策略，累计份数）===")
    agg = {s: {"holy": 0.0, "fungi": 0.0, "hell": 0.0} for s in idx}
    for r in recipes:
        for _ in range(max(50, runs // 4)):
            _, _, _, bz = simulate(r, vecs, idx, ["hell", "holy", "fungi"], rng, "priority", run_mode=run_mode)
            for s in idx:
                for z in ("holy", "fungi", "hell"):
                    agg[s][z] += bz[z][idx[s]]
    buckets = {"0-1 级": [], "2-4 级": [], "5-9 级": [], "10 级": []}
    for s in idx:
        t = spells[s]["tiers"]
        top = max(t, key=t.get) if t else -1
        b = "10 级" if top == 10 else ("5-9 级" if top >= 5 else ("2-4 级" if top >= 2 else "0-1 级"))
        buckets[b].append(s)
    print(f"{'主等级':10s}{'圣山':>9s}{'繁茂':>9s}{'地狱':>9s}   主要来源")
    for b, lst in buckets.items():
        tot = {z: sum(agg[s][z] for s in lst) for z in ("holy", "fungi", "hell")}
        if not lst:
            continue
        main = max(tot, key=tot.get)
        zh = {"holy": "圣山", "fungi": "繁茂", "hell": "地狱"}[main]
        print(f"{b:10s}{tot['holy']:9.0f}{tot['fungi']:9.0f}{tot['hell']:9.0f}   {zh}")


if __name__ == "__main__":
    main()
