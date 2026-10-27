# -*- coding: utf-8 -*-
"""把法术图标转成 base64，生成 src/icons.js（供 HTML 内嵌使用）。

用法：
    python scripts/impl/gen_icon_data.py

输出：
    src/icons.js   →  window.ICON_DATA = { 'LIGHT_SHOT': 'data:image/png;base64,...', ... }
数据来源：data/spell_weights.json 的 id 列表 + images/icons/wiki/<ID>_48.png
额外图标：images/icons/1.25.png → 'STAFF_125'、images/icons/1.5.png → 'STAFF_15'
          （法杖速度倍率图标，用于方案卡片）
"""
import base64
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICON_DIR = os.path.join(ROOT, "images", "icons", "wiki")
OUT = os.path.join(ROOT, "src", "icons.js")

# 额外图标：key -> 相对项目根的路径
EXTRA = {
    "STAFF_125": os.path.join("images", "icons", "1.25.png"),
    "STAFF_15": os.path.join("images", "icons", "1.5.png"),
}


def main():
    data = json.load(open(os.path.join(ROOT, "data", "spell_weights.json"), encoding="utf-8"))["spells"]
    entries, missing = [], []
    for rec in data:
        sid = rec["id"]
        path = os.path.join(ICON_DIR, sid + "_48.png")
        if not os.path.exists(path):
            missing.append(sid)
            continue
        b64 = base64.b64encode(open(path, "rb").read()).decode("ascii")
        entries.append("  %s: 'data:image/png;base64,%s'" % (json.dumps(sid), b64))

    for key, rel in EXTRA.items():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print("缺少额外图标：%s" % rel)
            continue
        b64 = base64.b64encode(open(path, "rb").read()).decode("ascii")
        entries.append("  %s: 'data:image/png;base64,%s'" % (json.dumps(key), b64))

    js = ("/* 自动生成，请勿手工编辑。生成脚本：scripts/impl/gen_icon_data.py */\n"
          "window.ICON_DATA = {\n" + ",\n".join(entries) + "\n};\n")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(js)
    print("已写入 %s：%d 个图标，%.1f KB" % (OUT, len(entries), len(js) / 1024))
    if missing:
        print("缺少图标（%d）：%s" % (len(missing), ", ".join(missing)))


if __name__ == "__main__":
    main()
