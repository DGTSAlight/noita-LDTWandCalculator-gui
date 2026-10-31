# -*- coding: utf-8 -*-
"""解析 gun_actions.lua 全量法术表，并对比「三条获取渠道」的单次命中率。

渠道（第7次分析结论）：
  A. 野生法杖（spawn_wands → g_items → wand_level_0X）
     引擎按 **类型过滤** 后按等级权重抽：GetRandomActionWithType(x,y,max_level,type,i)
     P = w_t(s) / Σ_{k<=max_level} W_k(type(s))
  B. 商店法术卡（generate_shop_item → GetRandomAction(x,y,biomeid,0)）
     全类型混抽：P = w_t(s) / Σ_{k<=max_level} W_k(全部)
  C. 宝箱随机卡（chest_random.lua make_random_card）
     全表均匀：P = 1 / N_valid（不看 spawn_level、不看权重）

输出：
  data/parsed/actions_full.json  —— 全量法术字段
  stdout                          —— 本项目 51 个法术的渠道对比表
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "data", "data", "scripts", "gun", "gun_actions.lua")
OUT = os.path.join(ROOT, "data", "parsed", "actions_full.json")
WEIGHTS = os.path.join(ROOT, "data", "spell_weights.json")

TYPE_NAME = {
    "ACTION_TYPE_PROJECTILE": 0,
    "ACTION_TYPE_STATIC_PROJECTILE": 1,
    "ACTION_TYPE_MODIFIER": 2,
    "ACTION_TYPE_DRAW_MANY": 3,
    "ACTION_TYPE_MATERIAL": 4,
    "ACTION_TYPE_OTHER": 5,
    "ACTION_TYPE_UTILITY": 6,
    "ACTION_TYPE_PASSIVE": 7,
}

FIELD = re.compile(
    r'^\s*(id|type|spawn_level|spawn_probability|spawn_requires_flag|price)\s*=\s*(.+?),?\s*(?:--.*)?$'
)


def parse():
    spells = []
    cur = None
    for line in open(SRC, encoding="utf-8", errors="ignore"):
        if re.match(r"^\t\{$", line):
            cur = {}
            continue
        if cur is None:
            continue
        if re.match(r"^\t\},?\s*$", line):
            if "id" in cur:
                spells.append(cur)
            cur = None
            continue
        m = FIELD.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k in ("id", "spawn_level", "spawn_probability", "spawn_requires_flag"):
            mm = re.match(r'^"([^"]*)"', v)
            cur[k] = mm.group(1) if mm else None
        elif k == "type":
            cur["type"] = TYPE_NAME.get(v, None)
        elif k == "price":
            cur["price"] = int(v) if v.isdigit() else None
    return spells


def tiers(s):
    lv = [int(x) for x in s.get("spawn_level", "").split(",") if x.strip() != ""]
    pr = [float(x) for x in s.get("spawn_probability", "").split(",") if x.strip() != ""]
    return dict(zip(lv, pr))


def main():
    spells = parse()
    by_id = {s["id"]: s for s in spells}

    # 等级 × 类型 权重和
    tot_all, tot_type = {}, {}
    for s in spells:
        t = tiers(s)
        ty = s.get("type")
        for lv, w in t.items():
            if w <= 0:
                continue
            tot_all[lv] = tot_all.get(lv, 0.0) + w
            tot_type.setdefault(ty, {})
            tot_type[ty][lv] = tot_type[ty].get(lv, 0.0) + w

    # 宝箱卡的候选池，严格照 chest_random.lua:make_random_card 的逻辑：
    #   有 flag → 已解锁才 valid；且 (仅在有 flag 的分支里) spawn_probability == "0" 才剔除
    #   无 flag → 直接 valid（哪怕 spawn_probability 是 "0"）
    valid = [
        s for s in spells
        if not (s.get("spawn_requires_flag") is not None and s.get("spawn_probability") == "0")
    ]
    n_valid = len(valid)

    def cum(d, m):
        return sum(v for k, v in d.items() if k <= m)

    def p_wand(sid, m):
        s = by_id[sid]
        t = tiers(s)
        ty = s.get("type")
        # 法杖只会抽这四类（gun_procedural.lua 16 处调用的类型集合）
        if ty not in (0, 1, 2, 3):
            return 0.0
        num = sum(w for lv, w in t.items() if lv <= m and w > 0)
        den = cum(tot_type.get(ty, {}), m)
        return num / den if den else 0.0

    def p_shop(sid, m):
        t = tiers(by_id[sid])
        num = sum(w for lv, w in t.items() if lv <= m and w > 0)
        den = cum(tot_all, m)
        return num / den if den else 0.0

    payload = {
        "note": "解析自 data/data/scripts/gun/gun_actions.lua；tiers = {等级: spawn_probability}",
        "n_actions": len(spells),
        "n_valid_for_chest": n_valid,
        "tier_weight_all": {str(k): round(v, 4) for k, v in sorted(tot_all.items())},
        "tier_weight_by_type": {
            str(ty): {str(k): round(v, 4) for k, v in sorted(d.items())}
            for ty, d in tot_type.items()
        },
        "spells": [
            {
                "id": s["id"],
                "type": s.get("type"),
                "tiers": tiers(s),
                "flag": s.get("spawn_requires_flag"),
                "price": s.get("price"),
            }
            for s in spells
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"法术条目 {len(spells)}，宝箱可抽池 {n_valid}")
    print("各等级全类型权重和：", {k: round(v, 1) for k, v in sorted(tot_all.items())})

    # 本项目 51 个法术
    proj = [s["id"] for s in json.load(open(WEIGHTS, encoding="utf-8"))["spells"]]
    print(f"\n=== 单次命中率对比（%），宝箱卡 = {100.0/n_valid:.3f}%（全表均匀） ===")
    hdr = f"{'id':22s}{'类型':>4s}{'tier':>6s}{'权重':>7s}{'法杖m=2':>9s}{'法杖m=4':>9s}{'商店m=4':>9s}{'商店m=10':>9s}{'宝箱':>9s}"
    print(hdr)
    for sid in proj:
        if sid not in by_id:
            print(f"{sid:22s}  [不在 gun_actions 里]")
            continue
        s = by_id[sid]
        t = tiers(s)
        top = max(t, key=lambda k: t[k]) if t else -1
        w = t.get(top, 0)
        print(
            f"{sid:22s}{str(s.get('type')):>4s}{top:>6d}{w:>7.2f}"
            f"{100*p_wand(sid,2):>9.3f}{100*p_wand(sid,4):>9.3f}"
            f"{100*p_shop(sid,4):>9.3f}{100*p_shop(sid,10):>9.3f}"
            f"{100.0/n_valid:>9.3f}"
        )

    # ---- 单根法杖的等级分布（max_level 为包含式上限）----
    print("\n=== 单根法杖抽到的法术等级分布（%，包含式上限 0..max_level，全类型）===")
    print("max_level " + "".join(f"{k:>7d}" for k in range(0, 8)) + f"{'10':>7s}")
    for m in [0, 1, 2, 3, 4, 5, 6, 10]:
        den = cum(tot_all, m)
        row = "".join(
            f"{100*tot_all.get(k,0)/den:>7.1f}" if k <= m else f"{'-':>7s}" for k in list(range(0, 8)) + [10]
        )
        print(f"{m:>9d} {row}")

    # ---- 三区域「单根野生法杖」的等级分布 ----
    print("\n=== 区域野生法杖的等级分布（%，按 g_items 等权混合）===")
    zones = {
        "繁茂洞穴 fungiforest": [2, 3, 4],
        "真菌洞穴 fungicave": [0, 1],
        "矿坑 coalmine": [0, 1],
    }
    print(f"{'区域':24s}" + "".join(f"{k:>7d}" for k in range(0, 7)))
    for name, ms in zones.items():
        row = []
        for k in range(0, 7):
            p = 0.0
            for m in ms:
                den = cum(tot_all, m)
                p += tot_all.get(k, 0) / den / len(ms) if k <= m and den else 0.0
            row.append(p)
        print(f"{name:24s}" + "".join(f"{100*v:>7.1f}" for v in row))


if __name__ == "__main__":
    main()
