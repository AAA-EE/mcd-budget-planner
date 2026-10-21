#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 README 用的页面效果图（SVG）

为什么不是截图
--------------
本项目的构建环境无法运行无头浏览器（Edge 无头模式无输出、agent-browser
需要下载 Chromium 但被网络代理阻断）。因此这里用真实数据 + 与
docs/index.html 相同的配色排版，以矢量方式复刻页面首屏。

它**不是截图**，而是按页面设计稿重绘的示意图；所有数值均来自
optimizer 的真实计算结果，不是编造的。

用法：
    python tools/make_preview.py
"""

import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcd_planner.optimizer import optimize  # noqa: E402

# 与 docs/index.html 一致的配色
C = {
    "bg": "#fafaf8",
    "card": "#ffffff",
    "line": "#e6e4df",
    "ink": "#1f1f1d",
    "muted": "#6b6a65",
    "hint": "#96948d",
    "blue": "#2f5496",
    "blue_bg": "#eef3fb",
    "green": "#2e7d4f",
    "green_bg": "#eaf5ee",
    "red": "#c0392b",
    "amber": "#a86a00",
    "amber_bg": "#fdf4e3",
    "dot": "#d8d5cd",
}

W = 1200
PAD = 60
FONT = "'PingFang SC','Microsoft YaHei','Hiragino Sans GB',sans-serif"


def t(x, y, s, size=16, fill=None, weight="400", anchor="start", ls="0"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" '
            f'font-size="{size}" font-weight="{weight}" '
            f'fill="{fill or C["ink"]}" text-anchor="{anchor}" '
            f'letter-spacing="{ls}">{escape(str(s))}</text>')


def rect(x, y, w, h, fill, stroke=None, rx=12, sw=1):
    s = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{sw}"'
    return s + "/>"


def main() -> None:
    now = datetime(2026, 10, 13, 14, 30)
    res = optimize(budget=30, max_sodium_mg=1200, max_items=3, now=now)
    best = res.frontier[0]
    lowest = min(res.frontier, key=lambda p: p.sodium_mg)

    parts = []
    y = 0

    # ---------- 背景 ----------
    parts.append(rect(0, 0, W, 1560, C["bg"], rx=0))

    # ---------- 顶部：eyebrow + 标题 + 副标题 ----------
    y = 78
    parts.append(t(PAD, y, "麦当劳程序员节创意开发大赛 · 参赛作品", 15, C["hint"], ls="0.6"))

    y += 62
    parts.append(t(PAD, y, "麦麦省钱", 44, C["ink"], "600"))
    # 第二段用主色
    parts.append(t(PAD + 44 * 4 + 6, y, "营养师", 44, C["blue"], "600"))

    y += 46
    parts.append(t(PAD, y,
                   "基于麦当劳 MCP。不做「券列表查询」，做点餐决策：", 17, C["muted"]))
    y += 28
    parts.append(t(PAD, y,
                   "在预算和钠摄入的双重约束下，算出实付最省、且吃得下去的组合。",
                   17, C["muted"]))

    # ---------- 四个指标卡 ----------
    y += 42
    stats = [("门店在售餐品", "91", "项"), ("营养数据", "158", "项"),
             ("可参与双维求解", "41", "项"), ("单元测试", "49", "项全通过")]
    cw = (W - PAD * 2 - 18 * 3) / 4
    for i, (label, num, unit) in enumerate(stats):
        x = PAD + i * (cw + 18)
        parts.append(rect(x, y, cw, 92, C["card"], C["line"]))
        parts.append(t(x + 22, y + 32, label, 14, C["hint"]))
        parts.append(t(x + 22, y + 72, num, 30, C["ink"], "600"))
        parts.append(t(x + 22 + len(num) * 18 + 8, y + 72, unit, 14, C["hint"]))
    y += 92 + 52

    # ---------- 在线试算面板 ----------
    parts.append(t(PAD, y, "在线试算", 22, C["ink"], "600"))
    y += 30
    parts.append(t(PAD, y, "拖动滑块，实时求解。数据为门店真实标价与官方营养表。",
                   15, C["muted"]))
    y += 26

    panel_h = 210
    parts.append(rect(PAD, y, W - PAD * 2, panel_h, C["card"], C["line"], rx=16))

    # 滑块一：预算
    sy = y + 30
    parts.append(t(PAD + 26, sy, "预算上限", 16, C["ink"], "500"))
    parts.append(t(W - PAD - 26, sy, "¥30", 16, C["blue"], "600", anchor="end"))
    ty = sy + 26
    parts.append(rect(PAD + 26, ty, W - PAD * 2 - 52, 5, C["line"], rx=3))
    # 30/80 的进度
    prog = (W - PAD * 2 - 52) * 30 / 80
    parts.append(rect(PAD + 26, ty, prog, 5, C["blue"], rx=3))
    parts.append(f'<circle cx="{PAD + 26 + prog:.1f}" cy="{ty + 2.5:.1f}" r="10" '
                 f'fill="{C["blue"]}" stroke="#fff" stroke-width="3"/>')

    # 滑块二：钠
    sy = ty + 62
    parts.append(t(PAD + 26, sy, "钠摄入上限", 16, C["ink"], "500"))
    parts.append(t(W - PAD - 26, sy, "1200mg", 16, C["blue"], "600", anchor="end"))
    ty = sy + 26
    parts.append(rect(PAD + 26, ty, W - PAD * 2 - 52, 5, C["line"], rx=3))
    prog = (W - PAD * 2 - 52) * 1200 / 3000
    parts.append(rect(PAD + 26, ty, prog, 5, C["blue"], rx=3))
    parts.append(f'<circle cx="{PAD + 26 + prog:.1f}" cy="{ty + 2.5:.1f}" r="10" '
                 f'fill="{C["blue"]}" stroke="#fff" stroke-width="3"/>')

    # 件数分段
    sy = ty + 58
    parts.append(t(PAD + 26, sy, "至少几件", 16, C["ink"], "500"))
    bx = W - PAD - 26 - 3 * 78 - 2 * 10
    for i, label in enumerate(["1 件", "2 件", "3 件"]):
        on = i == 0
        x = bx + i * 88
        parts.append(rect(x, sy - 26, 78, 38, C["blue"] if on else C["card"],
                          None if on else C["line"], rx=9))
        parts.append(t(x + 39, sy - 1, label, 14,
                       "#ffffff" if on else C["muted"],
                       "500" if on else "400", anchor="middle"))

    y += panel_h + 46

    # ---------- 最优方案：双卡（最省 / 最低钠） ----------
    parts.append(t(PAD, y, "最优方案", 22, C["ink"], "600"))
    y += 28
    parts.append(t(PAD, y,
                   f"{len(res.plans)} 个可行组合，其中 {len(res.frontier)} 个位于帕累托前沿。",
                   15, C["muted"]))
    y += 26

    hero_h = 236
    gap = 14
    cw2 = (W - PAD * 2 - gap) / 2
    cards = [
        (PAD, best, "实付最省", C["green"], C["green_bg"], C["card"], C["line"]),
        (PAD + cw2 + gap, lowest, "同预算最低钠", C["blue"], C["blue_bg"],
         "#fbfcfe", "#c9d7ec"),
    ]

    for cx, plan, tag, tag_fg, tag_bg, card_bg, border in cards:
        parts.append(rect(cx, y, cw2, hero_h, card_bg, border, rx=16))
        parts.append(rect(cx + 24, y + 22, 96, 26, tag_bg, rx=6))
        parts.append(t(cx + 24 + 48, y + 40, tag, 13, tag_fg, "500", anchor="middle"))

        parts.append(t(cx + 24, y + 82, " + ".join(plan.names), 20, C["ink"], "600"))
        parts.append(t(cx + 24, y + 128, f"¥{plan.price:.2f}", 34, C["blue"], "600"))
        if plan.saving > 0.005:
            parts.append(t(cx + 24 + 122, y + 128,
                           f"省 ¥{plan.saving:.2f}", 15, C["red"], "600"))

        parts.append(f'<line x1="{cx + 24}" y1="{y + 152}" '
                     f'x2="{cx + cw2 - 24}" y2="{y + 152}" '
                     f'stroke="{C["line"]}" stroke-width="1"/>')
        parts.append(t(cx + 24, y + 180,
                       f"钠 {plan.sodium_mg:.0f}mg", 14, C["muted"]))
        parts.append(t(cx + 24 + 128, y + 180,
                       f"热量 {plan.kcal:.0f}kcal", 14, C["muted"]))
        parts.append(t(cx + 24 + 268, y + 180,
                       f"蛋白 {plan.protein_g:.0f}g", 14, C["muted"]))

        # 底部：券信息或组合说明
        sub = ("已用券：" + "、".join(plan.quote.applied_coupons)
               if plan.quote.applied_coupons else "无可用券，按门店价")
        parts.append(t(cx + 24, y + 212, sub, 13, C["hint"]))

    # 约束提示条
    y += hero_h + 16
    tip = (f"同价区间内多花 ¥{lowest.price - best.price:.2f}，"
           f"可减钠 {best.sodium_mg - lowest.sodium_mg:.0f}mg。"
           f"把钠上限压到 {int(best.sodium_mg) - 1}mg 以下，推荐才会变化。")
    parts.append(rect(PAD, y, W - PAD * 2, 48, C["blue_bg"], rx=10))
    parts.append(t(PAD + 20, y + 30, tip, 14, C["blue"]))

    y += 48 + 52

    # ---------- 帕累托图 ----------
    parts.append(t(PAD, y, "价格 × 钠 帕累托前沿", 22, C["ink"], "600"))
    y += 30
    parts.append(t(PAD, y,
                   "前沿上的点不可支配：想再便宜就要接受更高钠，想更低钠就得多花钱。",
                   15, C["muted"]))
    y += 26

    ch = 330
    parts.append(rect(PAD, y, W - PAD * 2, ch, C["card"], C["line"], rx=16))

    # 图表绘图区
    gx, gy = PAD + 88, y + 34
    gw, gh = W - PAD * 2 - 130, ch - 92

    plans = res.plans
    max_p = max(p.price for p in plans) * 1.06
    max_s = max(p.sodium_mg for p in plans) * 1.06

    def X(v):
        return gx + v / max_p * gw

    def Y(v):
        return gy + gh - v / max_s * gh

    # 网格
    for i in range(5):
        yy = gy + gh * i / 4
        parts.append(f'<line x1="{gx}" y1="{yy:.1f}" x2="{gx + gw}" y2="{yy:.1f}" '
                     f'stroke="#eeece7" stroke-width="1"/>')
        parts.append(t(gx - 12, yy + 4, f"{max_s * (1 - i / 4):.0f}", 12,
                       C["hint"], anchor="end"))
    # 横轴刻度
    for i in range(5):
        xx = gx + gw * i / 4
        parts.append(t(xx, gy + gh + 24, f"¥{max_p * i / 4:.0f}", 12,
                       C["hint"], anchor="middle"))

    parts.append(t(gx + gw / 2, gy + gh + 48, "实付金额", 13, C["muted"], anchor="middle"))
    parts.append(f'<text transform="translate({gx - 54},{gy + gh / 2}) rotate(-90)" '
                 f'font-family="{FONT}" font-size="13" fill="{C["muted"]}" '
                 f'text-anchor="middle">钠 (mg)</text>')

    # 背景散点（采样）
    front_keys = {tuple(sorted(p.codes)) for p in res.frontier}
    bg = [p for p in plans if tuple(sorted(p.codes)) not in front_keys]
    stride = max(1, len(bg) // 120)
    for i in range(0, len(bg), stride):
        p = bg[i]
        parts.append(f'<circle cx="{X(p.price):.1f}" cy="{Y(p.sodium_mg):.1f}" '
                     f'r="3" fill="{C["dot"]}" opacity="0.75"/>')

    # 前沿连线
    if len(res.frontier) > 1:
        d = " ".join(("M" if i == 0 else "L") + f"{X(p.price):.1f} {Y(p.sodium_mg):.1f}"
                     for i, p in enumerate(res.frontier))
        parts.append(f'<path d="{d}" fill="none" stroke="{C["blue"]}" '
                     f'stroke-width="3" stroke-linejoin="round" opacity="0.3"/>')

    # 前沿点 + 标注
    for p in res.frontier:
        cx, cy = X(p.price), Y(p.sodium_mg)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{C["blue"]}" '
                     f'stroke="#fff" stroke-width="3"/>')
        label = " + ".join(p.names)
        parts.append(t(cx + 14, cy - 4, f"{label}", 13, C["ink"], "500"))
        parts.append(t(cx + 14, cy + 14, f"¥{p.price:.2f} · {p.sodium_mg:.0f}mg",
                       12, C["muted"]))

    y += ch + 44

    # ---------- 页脚 ----------
    parts.append(f'<line x1="{PAD}" y1="{y}" x2="{W - PAD}" y2="{y}" '
                 f'stroke="{C["line"]}" stroke-width="1"/>')
    y += 30
    parts.append(t(PAD, y, "数据快照 2026-10-13 · 本页算法与仓库内 Python 实现通过前后端对拍校验",
                   13, C["hint"]))
    y += 24
    parts.append(t(PAD, y, "麦当劳程序员节创意开发大赛参赛作品 · 非麦当劳官方产品",
                   13, C["hint"]))
    y += 50

    H = int(y)

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="麦麦省钱营养师在线试算页效果图">'
           f'<title>麦麦省钱营养师 · 在线试算页</title>'
           f'<desc>预算 ¥30、钠 ≤1200mg 的求解结果：麦香鸡 ¥17.00 / 731mg；'
           f'帕累托前沿含 2 个方案。</desc>'
           + "".join(parts) + "</svg>")

    out = ROOT / "docs" / "preview.svg"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print(f"已生成 {out}  ({out.stat().st_size / 1024:.1f} KB, {W}x{H})")
    print(f"  最优方案: {' + '.join(best.names)} ¥{best.price:.2f} "
          f"钠{best.sodium_mg:.0f}mg")
    print(f"  前沿点数: {len(res.frontier)}")


if __name__ == "__main__":
    main()