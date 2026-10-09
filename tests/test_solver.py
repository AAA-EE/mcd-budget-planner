# -*- coding: utf-8 -*-
"""
mcd_planner 单元测试

运行：
    python -m pytest tests/ -v
或无pytest 时：
    python tests/test_solver.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcd_planner.solver import (  # noqa: E402
    Constraints, classify, load_dataset, rank_by, recommend,
)


def _all_items():
    return load_dataset()


def test_dataset_loads():
    items = _all_items()
    assert len(items) == 158, f"期望 158 项，实际 {len(items)}"
    assert all(i.name for i in items)


def test_no_duplicate_names():
    names = [i.name for i in _all_items()]
    assert len(names) == len(set(names)), "数据集不应含重复餐品名"


def test_classify():
    assert classify("巨无霸") == "burger"
    assert classify("中薯条") == "side"
    assert classify("可乐中杯") == "drink"
    assert classify("草莓新地") == "dessert"


def test_rank_by_sodium_ascending():
    top = rank_by(_all_items(), "sodium_mg", limit=5)
    values = [i.sodium_mg for i in top]
    assert values == sorted(values), "钠排行必须升序"
    assert values[0] == 0


def test_rank_by_protein_descending():
    top = rank_by(_all_items(), "protein_g", reverse=True, limit=3)
    values = [i.protein_g for i in top]
    assert values == sorted(values, reverse=True)


def test_rank_by_invalid_metric():
    try:
        rank_by(_all_items(), "不存在的指标")
    except ValueError:
        return
    raise AssertionError("非法指标应抛 ValueError")


def test_constraints_respected():
    """推荐结果必须满足全部硬约束。"""
    c = Constraints(max_sodium_mg=600, max_kcal=500, min_protein_g=15)
    combos = recommend(_all_items(), c, max_size=3, limit=5)
    assert combos, "应至少找到一个可行组合"
    for totals, _ in combos:
        assert totals.sodium_mg <= 600, f"钠超标：{totals.sodium_mg}"
        assert totals.kcal <= 500, f"热量超标：{totals.kcal}"
        assert totals.protein_g >= 15, f"蛋白不足：{totals.protein_g}"


def test_exclude_items():
    items = _all_items()
    c = Constraints(max_kcal=600, exclude=frozenset({"巨无霸"}))
    combos = recommend(items, c, max_size=2, limit=3)
    for totals, _ in combos:
        for it in totals.items:
            assert it.name != "巨无霸"


def test_satiety_penalty_avoids_drink_only_combos():
    """
    回归测试：控钠午餐不应推荐成「三杯咖啡」。
    要求组合热量达到一餐下限（>=200kcal 视为饱腹达标，或至少不全是饮品）。
    """
    c = Constraints(max_sodium_mg=600, max_kcal=500)
    combos = recommend(_all_items(), c, max_size=3, limit=5)
    assert combos
    for totals, _ in combos:
        has_solid = any(i.category in ("burger", "side") for i in totals.items)
        assert has_solid, f"午餐组合缺少主食/小食：{[i.name for i in totals.items]}"


def test_category_diversity():
    """同类别最多 2 项，避免堆砌同类。"""
    c = Constraints(max_kcal=800, max_sodium_mg=800)
    combos = recommend(_all_items(), c, max_size=3, limit=8)
    for totals, _ in combos:
        cats = [i.category for i in totals.items]
        for cat in set(cats):
            assert cats.count(cat) <= 2, f"类别 {cat} 出现 {cats.count(cat)} 次"


def test_sodium_aware_ranking():
    """评分更低的组合，钠含量不应显著更高。"""
    c = Constraints(max_kcal=600, max_sodium_mg=900)
    combos = recommend(_all_items(), c, max_size=3, limit=5)
    if len(combos) >= 2:
        best = combos[0][0]
        worst = combos[-1][0]
        # 首位组合钠含量不应高于末位组合 3 倍以上
        assert best.sodium_mg <= max(worst.sodium_mg * 3, 300), \
            "评分排序未体现控钠优先"


def test_totals_summary():
    items = _all_items()
    burger = next(i for i in items if i.name == "汉堡包")
    from mcd_planner.solver import NutritionTotals
    t = NutritionTotals()
    t.add(burger)
    t.add(burger, qty=2)
    assert t.kcal == burger.kcal * 3
    assert len(t.items) == 3
    assert "汉堡包" in t.summary()


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
    print(f"\n共 {len(tests)} 项，通过 {passed}，失败 {failed}")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)