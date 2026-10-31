# -*- coding: utf-8 -*-
"""把 src/ 下的源码组装成单文件 HTML（最终交付物）。

用法：
    python scripts/impl/build.py [输出文件名]

组装规则（模板 src/template.html 中的占位符）：
    <!--__STYLE__-->    ← src/style.css
    /*__DATA__*/        ← data/spell_weights.json（内联为 window.SPELL_DATA）
    /*__ICONS__*/       ← src/icons.js
    /*__ENGINE__*/      ← src/engine.js
    /*__APP__*/         ← src/app.js

模板里的 {{VERSION}} 会替换成输出文件名中的版本号（`_v0.2.2.html` → `v0.2.2`），
避免标题版本号与文件名脱节。

依赖：src/template.html、src/style.css、src/app.js（阶段 3 产出）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
DEFAULT_OUT = "跃迁法术收集计算器GUI_v0.2.2.html"

REQUIRED = ["template.html", "style.css", "engine.js", "icons.js", "app.js"]
DATA_JSON = os.path.join(ROOT, "data", "spell_weights.json")


def read(name):
    path = os.path.join(SRC, name)
    if not os.path.exists(path):
        raise SystemExit("缺少源文件：src/%s（阶段 3 完成后才可构建）" % name)
    return open(path, encoding="utf-8").read()


def main():
    out_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    missing = [n for n in REQUIRED if not os.path.exists(os.path.join(SRC, n))]
    if missing:
        print("无法构建，缺少：")
        for m in missing:
            print("  src/" + m)
        print("\n（engine.js 与 icons.js 已就绪，template/style/app 属于阶段 3）")
        return 1

    if not os.path.exists(DATA_JSON):
        raise SystemExit("缺少数据：data/spell_weights.json（请先运行 scripts/wiki/collect_weights.py）")
    data_js = "window.SPELL_DATA = " + open(DATA_JSON, encoding="utf-8").read() + ";"

    html = read("template.html")
    # 版本号从输出文件名取，避免标题与文件名各写一份而漂移
    import re
    m = re.search(r"_v(\d+\.\d+\.\d+)\.html$", out_name)
    version = "v" + m.group(1) if m else "dev"
    html = html.replace("{{VERSION}}", version)

    parts = {
        "<!--__STYLE__-->": "<style>\n" + read("style.css") + "\n</style>",
        "/*__DATA__*/": data_js,
        "/*__ICONS__*/": read("icons.js"),
        "/*__ENGINE__*/": read("engine.js"),
        "/*__APP__*/": read("app.js"),
    }
    for k, v in parts.items():
        if k not in html:
            raise SystemExit("模板缺少占位符：%s" % k)
        html = html.replace(k, v)

    out = os.path.join(ROOT, out_name)
    open(out, "w", encoding="utf-8").write(html)
    print("已生成 %s（%.1f KB）" % (out_name, len(html.encode("utf-8")) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
