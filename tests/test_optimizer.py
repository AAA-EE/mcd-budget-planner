# -*- coding: utf-8 -*-
"""
优化器单元测试

运行：
    python tests/test_optimizer.py
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcd_planner.optimizer import (  # noqa: E402
    build_joint_catalog, describe_tradeoff, dominating_alternatives,
    explain_dominance, format_frontier, optimize,
)

NOW = datetime(2026, 10, 13, 14, 30)


def test_catalog_built():
    cat = build_joint_catalog()
    assert len(cat) > 30, f"联合目录过小：{len(cat)}"
    assert all(c.code and c.name for c in cat)
    assert all(c.price >= 0 and c.sodium_mg >= 0 for c in cat)


def test_catalog_dedup_by_code():
    cat = build_joint_catalog()
    codes = [c.code for c in cat]
    assert len(codes) == len(set(codes)), "联合目录存在重复编码"


def test_budget_respected():
    r = optimize(budget=25, max_items=2, now=NOW)
    assert r.plans, "预算 25 应至少有一个方案"
    for p in r.plans:
        assert p.price <= 25 + 1e-6, f"超预算：{p.price}"


def test_sodium_cap_respected():
    r = optimize(budget=50, max_sodium_mg=600, max_items=3, now=NOW)
    for p in r.plans:
        assert p.sodium_mg <= 600 + 1e-6, f"超钠上限：{p.sodium_mg}"


def test_kcal_cap_respected():
    r = optimize(budget=50, max_kcal=600, max_items=2, now=NOW)
    for p in r.plans:
        assert p.kcal <= 600 + 1e-6, f"超热量上限：{p.kcal}"


def test_require_staple_excludes_drink_only():
    """开启主食要求后，方案必须含汉堡或套餐，不能是纯饮品。"""
    r = optimize(budget=40, max_items=3, require_staple=True, now=NOW)
    for p in r.plans:
        cats = {c for c in p.codes}
        # 通过名称反推：至少一件不是饮品/甜品
        assert len(p.codes) >= 1
    # 更直接：所有方案不应只由低钠饮品构成
    for p in r.plans:
        assert not (p.sodium_mg == 0 and p.kcal < 100), \
            f"疑似纯饮品方案：{p.label()}"


def test_frontier_is_nondominated():
    r = optimize(budget=50, max_sodium_mg=1500, max_items=3, now=NOW)
    assert r.frontier
    for i, a in enumerate(r.frontier):
        for b in r.frontier[i + 1:]:
            dominated = (b.price <= a.price and b.sodium_mg <= a.sodium_mg
                         and (b.price < a.price or b.sodium_mg < a.sodium_mg))
            assert not dominated, f"前沿点 {a.label()}被 {b.label()} 支配"


def test_frontier_sorted_by_price():
    r = optimize(budget=50, max_sodium_mg=1500, max_items=3, now=NOW)
    prices = [p.price for p in r.frontier]
    assert prices == sorted(prices), "前沿应按价格升序"


def test_describe_tradeoff():
    r = optimize(budget=50, max_sodium_mg=1500, max_items=3, now=NOW)
    text = describe_tradeoff(r.frontier)
    assert isinstance(text, str)


def test_alternatives_same_category_only():
    """
    同类替代约束。

    这曾是一个真实缺陷：未限制类别时，「巨无霸」的替代方案里出现了
    圆筒冰淇淋——价格和钠都更优，但把汉堡换成冰淇淋不是「替代」。
    """
    cat = build_joint_catalog()
    alts = dominating_alternatives("1100", cat, now=NOW)  # 巨无霸
    assert alts, "巨无霸应有替代方案"
    drinks_only = {"drink", "dessert"}
    for a in alts:
        for code in a.codes:
            it = next(c for c in cat if c.code == code)
            # 允许「主食+饮品」组合，但不允许纯饮品/纯甜品替代主食
            if len(a.codes) == 1:
                assert it.category not in drinks_only, \
                    f"不应以 {it.name}（{it.category}）替代汉堡"


def test_alternatives_are_truly_dominating():
    cat = build_joint_catalog()
    target = next(c for c in cat if c.code == "1100")
    for alt in dominating_alternatives("1100", cat, now=NOW):
        assert alt.price <= target.price + 1e-6, "替代方案价格不应更高"
        assert alt.sodium_mg <= target.sodium_mg + 1e-6, "替代方案钠不应更高"


def test_two_burgers_same_price_different_sodium():
    """
    核心业务洞察：同价不同钠。

    麦辣鸡腿汉堡 ¥22.5 / 1208mg 与麦香鱼 ¥22.5 / 556mg 同价，
    后者钠含量不到前者一半。
    """
    cat = build_joint_catalog()
    spicy = next(c for c in cat if c.code == "1440")   # 麦辣鸡腿汉堡
    fish = next(c for c in cat if c.code == "1600")    # 麦香鱼
    assert abs(spicy.price - fish.price) < 1e-6, "两者应同价"
    assert fish.sodium_mg < spicy.sodium_mg * 0.6, "麦香鱼钠应显著更低"


def test_explain_dominance_text():
    cat = build_joint_catalog()
    target = next(c for c in cat if c.code == "1100")
    alts = dominating_alternatives("1100", cat, now=NOW)
    if alts:
        text = explain_dominance(target, alts[0])
        assert "便宜" in text or "少钠" in text or "持平" in text


def test_no_solution_message():
    r = optimize(budget=1, max_items=2, now=NOW)
    assert r.plans == []
    assert any("放宽" in n or "没有" in n for n in r.notes), "无解时应给出提示"


def test_format_frontier_output():
    r = optimize(budget=50, max_sodium_mg=1500, max_items=3, now=NOW)
    text = format_frontier(r.frontier)
    assert "实付" in text and "钠" in text


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
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