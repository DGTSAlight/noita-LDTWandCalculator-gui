# -*- coding: utf-8 -*-
"""v0.1.1 数据迁移：把单角色 role 升级为多角色 roles，并移除不参与跃迁的暴击增强。

用法：
    python scripts/impl/migrate_roles_v011.py

改动：
    1. data/spell_targets.json   → 每个法术新增 roles 数组（保留 role 作兼容）
    2. data/spell_weights.json   → 同步 roles；删除 CRITICAL_HIT
    3. 与 scripts/wiki/collect_weights.py 的 roles 透传保持一致
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 一个法术可以同时属于多个功能分区（例如蓝拳既是速度修正也是伤害修正）
ROLES = {
    "LIGHT_SHOT": ["speed", "damage"],
    "SPEED": ["speed"],
    "ACCELERATING_SHOT": ["speed"],
    "DECELERATING_SHOT": ["speed"],
    "EXPLOSIVE_PROJECTILE": ["speed"],
    "HEAVY_SHOT": ["speed"],
    "FIZZLE": ["speed"],
    "SINEWAVE": ["speed"],
    "CHAOTIC_ARC": ["speed"],
    "SLIMEBALL": ["speed"],
    "PHASING_ARC": ["speed", "copy"],
    "LIFETIME": ["time"],
    "LIFETIME_DOWN": ["time"],
    "ZERO_DAMAGE": ["time"],
    "FLY_UPWARDS": ["copy"],
    "FLY_DOWNWARDS": ["copy"],
    "TENTACLE_TIMER": ["carrier"],
    "BLACK_HOLE": ["carrier", "calibrator"],
    "BLACK_HOLE_DEATH_TRIGGER": ["carrier", "calibrator"],
    "LIGHTNING": ["carrier"],
    "SLOW_BULLET_TIMER": ["carrier"],
    "MEGALASER": ["carrier"],
    "X_RAY": ["carrier"],
    "LARPA_CHAOS": ["limit"],
    "LARPA_CHAOS_2": ["limit"],
    "ENERGY_SHIELD_SHOT": ["limit"],
    "QUANTUM_SPLIT": ["limit"],
    "TELEPORT_PROJECTILE_CLOSER": ["payload"],
    "CASTER_CAST": ["payload"],
    "SWAPPER_PROJECTILE": ["payload"],
    "EXPLODING_DEER": ["payload"],
    "TRUE_ORBIT": ["payload"],
    "ORBIT_LARPA": ["payload"],
    "DAMAGE": ["damage"],
    "LINE_ARC": ["calibrator", "damage"],
    "HORIZONTAL_ARC": ["calibrator", "damage"],
    "NOLLA": ["calibrator"],
    "DELAYED_SPELL": ["calibrator"],
    "RESET": ["aux"],
    "ADD_TRIGGER": ["trigger"],
    "ADD_TIMER": ["trigger"],
    "ADD_DEATH_TRIGGER": ["trigger"],
    "IF_HP": ["aux"],
    "IF_HALF": ["aux"],
    "IF_END": ["aux"],
    "TAU": ["aux"],
    "GAMMA": ["aux"],
    "DIVIDE_2": ["dn"],
    "DIVIDE_3": ["dn"],
    "DIVIDE_4": ["dn"],
    "DIVIDE_10": ["dn"],
}

# 不参与跃迁 / 由用户配置决定 / 跃迁用不上，直接从数据中移除
#   CRITICAL_HIT   暴击增强：不属于伤害修正
#   BURST_2/3/4    多重法术：涉及用户具体配置需要的抽取数，不该由本工具决定
#   IF_ELSE / IF_ENEMY / IF_PROJECTILE  各种跃迁配置都用不上
DROP = {"CRITICAL_HIT", "BURST_2", "BURST_3", "BURST_4",
        "IF_ELSE", "IF_ENEMY", "IF_PROJECTILE"}


def migrate_targets():
    path = os.path.join(ROOT, "data", "spell_targets.json")
    d = json.load(open(path, encoding="utf-8"))
    kept, dropped = [], []
    for rec in d["spells"]:
        sid = rec["id"]
        if sid in DROP:
            dropped.append(sid)
            continue
        roles = ROLES.get(sid) or [rec.get("role", "aux")]
        rec["roles"] = roles
        rec["role"] = roles[0]          # 兼容旧字段
        kept.append(rec)
    d["spells"] = kept
    d["_角色说明"] = ("roles 为多角色数组：同一法术可同时出现在多个功能分区。"
                     "取值：speed 速度修正 / damage 伤害修正 / calibrator 校准器 / "
                     "carrier 跃迁载体 / limit 存在时间限制器 / time 存在时间修正 / "
                     "payload 载荷与返回 / trigger 追加触发 / dn 一分为多 / "
                     "copy 复制对象（被 Dn 复制的法术）/ aux 其他辅助")
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("spell_targets.json：%d 条，移除 %s" % (len(kept), dropped or "无"))


def migrate_weights():
    path = os.path.join(ROOT, "data", "spell_weights.json")
    d = json.load(open(path, encoding="utf-8"))
    kept, dropped = [], []
    for rec in d["spells"]:
        sid = rec["id"]
        if sid in DROP:
            dropped.append(sid)
            continue
        roles = ROLES.get(sid) or [rec.get("role", "aux")]
        rec["roles"] = roles
        rec["role"] = roles[0]
        kept.append(rec)
    d["spells"] = kept
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("spell_weights.json：%d 条，移除 %s" % (len(kept), dropped or "无"))


if __name__ == "__main__":
    migrate_targets()
    migrate_weights()
