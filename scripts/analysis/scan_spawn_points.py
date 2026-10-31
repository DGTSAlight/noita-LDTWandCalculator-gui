# -*- coding: utf-8 -*-
"""扫描解包文件里的「生成点」：wang 模板颜色计数、像素场景内嵌标记、群系地图行列。

用途（第7次分析）：
  1. wang 模板（data/data/wang_tiles/*.png）——每个有色像素 = 一次该生成函数的调用。
     颜色表 = data/scripts/wang_scripts.csv（全局）+ 各群系 RegisterSpawnFunction（本地）。
  2. 像素场景（data/data/biome_impl/**/*.png）——场景里可以内嵌生成色，
     例如 wand_altar.png 里有 1 个 #50a0f0（= spawn_wands）。
  3. 群系地图（data/data/biome_impl/biome_map.png，70x48，每格 512px）——定位圣山等群系所在行。

用法：
  python scripts/analysis/scan_spawn_points.py wang
  python scripts/analysis/scan_spawn_points.py scene 50a0f0
  python scripts/analysis/scan_spawn_points.py map temple
"""
import collections
import csv
import os
import re
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "data", "data")


def load_global_colors():
    out = {}
    with open(os.path.join(D, "scripts", "wang_scripts.csv"), encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#"):
                continue
            out[int(row[0].strip(), 16) & 0xFFFFFF] = row[1].strip()
    return out


def load_local_colors(lua_name):
    out = {}
    p = os.path.join(D, "scripts", "biomes", lua_name + ".lua")
    if not os.path.exists(p):
        return out
    txt = open(p, encoding="utf-8", errors="ignore").read()
    for m in re.finditer(r'RegisterSpawnFunction\(\s*0x([0-9a-fA-F]+)\s*,\s*"([^"]+)"', txt):
        out[int(m.group(1), 16) & 0xFFFFFF] = m.group(2)
    return out


def rgb_to_int(c):
    return (c[0] << 16) | (c[1] << 8) | c[2]


def cmd_wang(zones):
    glob = load_global_colors()
    for z in zones:
        p = os.path.join(D, "wang_tiles", z + ".png")
        if not os.path.exists(p):
            print(f"!! 缺少 {z}.png")
            continue
        im = Image.open(p).convert("RGB")
        w, h = im.size
        cnt = collections.Counter(list(im.getdata()))
        regs = dict(glob)
        regs.update(load_local_colors(z))
        agg = collections.Counter()
        for c, n in cnt.items():
            fn = regs.get(rgb_to_int(c))
            if fn:
                agg[fn] += n
        print(f"\n### {z}.png  {w}x{h} = {w*h} 格")
        for fn, n in agg.most_common():
            print(f"   {fn:32s} {n:6d}  ({100*n/(w*h):5.2f}%)")


def cmd_scene(color_hex, limit=700):
    target = tuple(int(color_hex[i:i + 2], 16) for i in (0, 2, 4))
    hits = []
    for base, _, files in os.walk(os.path.join(D, "biome_impl")):
        for fn in files:
            if not fn.lower().endswith(".png"):
                continue
            p = os.path.join(base, fn)
            try:
                im = Image.open(p).convert("RGB")
            except Exception:
                continue
            if im.size[0] > limit or im.size[1] > limit:
                continue
            cnt = collections.Counter(list(im.getdata()))
            if target in cnt:
                hits.append((os.path.relpath(p, os.path.join(D, "biome_impl")), im.size, cnt[target]))
    print(f"颜色 #{color_hex} 出现在 {len(hits)} 个场景里")
    for h in hits:
        print("  ", h)


def cmd_map(keyword):
    txt = open(os.path.join(D, "biome", "_biomes_all.xml"), encoding="utf-8", errors="ignore").read()
    c2n = {
        int(c[2:], 16): fn.split("/")[-1].replace(".xml", "")
        for fn, c in re.findall(r'biome_filename="([^"]+)"[^>]*?color="([0-9a-fA-F]{8})"', txt, re.S)
    }
    im = Image.open(os.path.join(D, "biome_impl", "biome_map.png")).convert("RGB")
    w, h = im.size
    px = im.load()
    rows = collections.defaultdict(collections.Counter)
    for y in range(h):
        for x in range(w):
            n = c2n.get(rgb_to_int(px[x, y]))
            if n and keyword in n:
                rows[n][y] += 1
    print(f"biome_map {w}x{h}（每格 512px），名称含 '{keyword}' 的群系：")
    for n in sorted(rows):
        print(f"\n{n}: 共 {sum(rows[n].values())} 格")
        for r in sorted(rows[n]):
            print(f"   row {r:2d}  y {r*512}~{r*512+511}  {rows[n][r]} 格")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "wang"
    if mode == "wang":
        zones = sys.argv[2:] or ["fungiforest", "fungicave", "coalmine", "coalmine_alt", "the_end"]
        cmd_wang(zones)
    elif mode == "scene":
        cmd_scene(sys.argv[2] if len(sys.argv) > 2 else "50a0f0")
    elif mode == "map":
        cmd_map(sys.argv[2] if len(sys.argv) > 2 else "temple")
    else:
        print(__doc__)
