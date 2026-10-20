#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化器演示：价格 × 钠 的帕累托前沿

无需 MCP、无需网络，直接运行：
    python examples/demo_optimize.py
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcd_planner.optimizer import (  # noqa: E402
    build_joint_catalog, describe_tradeoff, dominating_alternatives,
    explain_dominance, format_frontier, optimize,
)

NOW = datetime(2026, 10, 13, 14, 30)   # 周二下午


def banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)


def main() -> None:
    catalog = build_joint_catalog()

    banner("数据装配")
    print(f"同时具备价格与营养的餐品：{len(catalog)} 项")
    print("（套餐与新品因缺少对应营养数据，已排除，不猜测）")

    # ---- 场景一：30 元预算，控钠 ----
    banner("场景一｜预算 ¥30，钠 ≤ 1200mg，最多 3 件")
    r = optimize(budget=30, max_sodium_mg=1200, max_items=3, now=NOW)
    print(f"可行组合 {len(r.plans)} 个，进入帕累托前沿 {len(r.frontier)} 个")
    print()
    print(format_frontier(r.frontier))
    print()
    print(describe_tradeoff(r.frontier))

    # ---- 场景二：放宽预算看前沿形状 ----
    banner("场景二｜不限预算，钠 ≤ 1500mg，最多 3 件")
    r2 = optimize(budget=60, max_sodium_mg=1500, max_items=3, now=NOW)
    print(f"可行组合 {len(r2.plans)} 个，前沿仅 {len(r2.frontier)} 个")
    print("—— 说明绝大多数组合都能被某个更优选项替代。")
    print()
    print(format_frontier(r2.frontier))

    # ---- 场景三：同价不同钠 ----
    banner("场景三｜同价不同钠：这是本项目的核心发现")
    spicy = next(c for c in catalog if c.code == "1440")   # 麦辣鸡腿汉堡
    fish = next(c for c in catalog if c.code == "1600")    # 麦香鱼
    print(f"  {spicy.name:<12} ¥{spicy.price:>5.2f}  钠 {spicy.sodium_mg:>5.0f}mg"
          f"  热量 {spicy.kcal:>4.0f}kcal")
    print(f"  {fish.name:<12} ¥{fish.price:>5.2f}  钠 {fish.sodium_mg:>5.0f}mg"
          f"  热量 {fish.kcal:>4.0f}kcal")
    print(f"\n  两者同为 ¥{spicy.price:.2f}，但后者钠少 "
          f"{spicy.sodium_mg - fish.sodium_mg:.0f}mg"
          f"（{(1 - fish.sodium_mg / spicy.sodium_mg) * 100:.0f}%）。")
    print("  同样的钱，选哪个更值得，一目了然。")

    # ---- 场景四：我已经想吃 X 了 ----
    banner("场景四｜「我就想吃巨无霸」—— 有更好的同类替代吗")
    for code in ("1100", "1440", "511781"):
        tgt = next(c for c in catalog if c.code == code)
        alts = dominating_alternatives(code, catalog, now=NOW)
        print(f"\n目标：{tgt.name}　¥{tgt.price:.2f}　钠 {tgt.sodium_mg:.0f}mg")
        if not alts:
            print("  → 同类里没有更便宜又更低钠的选择，这个选择本身就是划算的。")
            continue
        for a in alts[:4]:
            print(f"  → ¥{a.price:>5.2f} 钠 {a.sodium_mg:>4.0f}mg  "
                  f"{a.label():<22} {explain_dominance(tgt, a)}")

    # ---- 场景五：券的影响 ----
    banner("场景五｜券的真实效果（定价引擎直算）")
    from mcd_planner.pricing import load_coupons, load_menu, price_basket

    menu = load_menu()
    coupons = load_coupons()

    demo = [
        ("9900012387", "中薯条买一送一", "券商品本身即优惠 SKU"),
        ("9900016371", "王牌小食拼", "券商品本身即优惠 SKU"),
        ("1100", "巨无霸", "无对应券，按门店价"),
    ]
    for code, label, note in demo:
        q = price_basket([(code, 1)], menu, coupons, now=NOW)
        flag = "用券" if q.applied_coupons else "无券"
        print(f"  {label:<14} 原价 ¥{q.list_total:>6.2f} → "
              f"实付 ¥{q.paid_total:>6.2f}  省 ¥{q.saving:>5.2f}  [{flag}]  {note}")

    print("\n  能用的券：", end="")
    usable = [c for c in coupons if c.is_time_valid(NOW)[0]]
    if usable:
        print("、".join(c.title for c in usable))
    else:
        print(f"当前时刻（{NOW:%m-%d %H:%M}）无可用券")

    print("\n  不可用的券及原因（前 3 条）：")
    for c in coupons:
        ok, reason = c.is_time_valid(NOW)
        if not ok:
            print(f"    × {c.title}：{reason}")
            if len([1 for x in coupons[:coupons.index(c)]
                    if not x.is_time_valid(NOW)[0]]) >= 2:
                break

    print("\n注：券的可用性严格按当前时间与时段判定，不臆造可叠加组合。")

    print("\n" + "-" * 68)
    print("以上均为离线计算，不含 MCP 实时数据。")
    print("接入 MCP 后，券与菜单取实时值，算法不变。")


if __name__ == "__main__":
    main()