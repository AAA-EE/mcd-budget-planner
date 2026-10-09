#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行入口：离线演示营养约束求解

无需 MCP、无需网络，直接运行：
    python examples/demo_offline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcd_planner.solver import (  # noqa: E402
    Constraints, load_dataset, rank_by, recommend,
)


def banner(title: str) -> None:
    print("\n" + "=" * 62)
    print(f"  {title}")
    print("=" * 62)


def main() -> None:
    items = load_dataset()
    banner("麦当劳营养数据集已加载")
    print(f"餐品总数：{len(items)} 项")

    # ---- 场景一：控钠（实测发现钠含量差异巨大）----
    banner("场景一：控钠午餐｜钠 ≤ 600mg 且 热量 ≤ 500kcal")
    c1 = Constraints(max_sodium_mg=600, max_kcal=500)
    for totals, score in recommend(items, c1, max_size=3, limit=4):
        print(f"\n[评分 {score:.2f}]")
        print(totals.summary())

    # ---- 场景二：高蛋白低热量 ----
    banner("场景二：高蛋白早餐｜蛋白 ≥ 20g 且 热量 ≤ 400kcal")
    c2 = Constraints(min_protein_g=20, max_kcal=400)
    for totals, _ in recommend(items, c2, max_size=3, limit=3):
        print()
        print(totals.summary())

    # ---- 场景三：极低钠单品排行 ----
    banner("场景三：钠含量最低的 8 款餐品（单品排行）")
    for it in rank_by(items, "sodium_mg", limit=8):
        print(f"  {it.sodium_mg:>6.0f}mg  {it.kcal:>4.0f}kcal  {it.name}")

    # ---- 场景四：只选饮品，找出零热量替换方案 ----
    banner("场景四：零热量饮品（用于替换含糖饮料）")
    drinks = [i for i in items if i.category == "drink" and i.kcal <= 15]
    for it in drinks:
        print(f"  {it.kcal:>4.0f}kcal  钠 {it.sodium_mg:>3.0f}mg  {it.name}")

    # ---- 场景五：同价位高蛋白密度 ----
    banner("场景五：蛋白质密度排行（每克蛋白质对应热量，越低越优）")
    ranked = sorted(
        [i for i in items if i.protein_g >= 10 and i.category in ("burger", "side")],
        key=lambda x: x.kcal_per_protein,
    )[:8]
    for it in ranked:
        print(f"  {it.kcal_per_protein:>5.1f} kcal/g蛋白  "
              f"{it.name}（蛋白 {it.protein_g:.0f}g）")

    print("\n提示：以上为离线营养分析，不含实时价格与优惠券。")
    print("     接入 MCP 后可叠加门店可用券与实付试算。")


if __name__ == "__main__":
    main()