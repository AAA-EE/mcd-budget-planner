# -*- coding: utf-8 -*-
"""
定价引擎与帕累托前沿的单元测试

运行：
    python tests/test_pricing.py
"""

import sys
from datetime import datetime, time as dtime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcd_planner.pricing import (  # noqa: E402
    STACK_GREEDY, STACK_SINGLE, Coupon, MenuItem,
    can_stack, conflict_reason, load_coupons, load_menu, price_basket,
)
from mcd_planner.solver import (  # noqa: E402
    load_dataset, pareto_frontier,
)

MON_2PM = datetime(2026, 10, 13, 14, 30)   # 周二下午
TUE_8AM = datetime(2026, 10, 20, 8, 0)     # 周二早上（早餐时段）


# --------------------------------------------------------------------------- #
# 定价引擎
# --------------------------------------------------------------------------- #

def test_menu_loads():
    menu = load_menu()
    assert len(menu) > 80, f"菜单项过少：{len(menu)}"
    assert all(m.code and m.name for m in menu.values())


def test_coupons_load():
    coupons = load_coupons()
    assert len(coupons) >= 2
    assert all(c.coupon_id for c in coupons)


def test_no_coupon_baseline():
    """不用券时，实付应等于门店现价。"""
    menu = load_menu()
    q = price_basket([("1100", 1)], menu, [], now=MON_2PM)
    assert q.paid_total == 25.5, f"巨无霸应为 25.5，实际 {q.paid_total}"
    assert q.applied_coupons == []


def test_saving_uses_original_price():
    """
    划线价作为对照基准。

    这曾是一个真实缺陷：用门店现价做基准时，「中薯条买一送一」
    （现价 13.5 已是券后价）会算出「省 ¥0.00」。
    """
    menu = load_menu()
    q = price_basket([("9900012387", 1)], menu, [], now=MON_2PM)
    assert q.list_total == 27.0, f"划线价应为 27，实际 {q.list_total}"
    assert q.paid_total == 13.5
    assert q.saving == 13.5, f"应省 13.5，实际 {q.saving}"


def test_coupon_applied_within_window():
    """在券的有效时段内应命中。"""
    menu, coupons = load_menu(), load_coupons()
    q = price_basket([("9900012387", 1)], menu, coupons, now=MON_2PM)
    assert "中薯条买一送一" in q.applied_coupons


def test_coupon_rejected_after_expiry():
    """过期后不应命中，且要给出原因。"""
    menu, coupons = load_menu(), load_coupons()
    later = datetime(2026, 10, 20, 14, 30)   # 已过 10-16
    q = price_basket([("9900012387", 1)], menu, coupons, now=later)
    assert "中薯条买一送一" not in q.applied_coupons
    assert any("已过期" in n for n in q.notes), "应提示券已过期"


def test_breakfast_coupon_time_window():
    """
    早餐券的时间约束。

    注意：真实早餐券的 valid_to 与 time_window 结束时间同为 10:29，
    因此下午测试时先触发「已过期」而非「不在时段」——两者都是正确的拒绝理由。
    此处分别验证：真实券的时段拒绝，以及纯时段约束（valid_to 更晚时）。
    """
    coupons = load_coupons()
    bk = next(c for c in coupons if "早餐" in c.title)

    ok_morning, _ = bk.is_time_valid(datetime(2026, 10, 14, 8, 0))
    assert ok_morning, "早餐时段应可用"

    ok_noon, reason = bk.is_time_valid(datetime(2026, 10, 14, 14, 0))
    assert not ok_noon, "下午应不可用"
    assert ("时段" in reason) or ("已过期" in reason), f"拒绝理由不明确：{reason}"

    # 纯时段约束：有效期覆盖全天，但只允许早餐时段
    window_only = Coupon(
        "W1", "仅早餐时段", "special",
        product_codes=frozenset({"4810"}), coupon_price=5.0,
        valid_from=datetime(2026, 10, 1, 0, 0),
        valid_to=datetime(2026, 10, 31, 23, 59),
        time_window=(dtime(5, 0), dtime(10, 29)),
    )
    ok_w, _ = window_only.is_time_valid(datetime(2026, 10, 14, 8, 0))
    no_w, why = window_only.is_time_valid(datetime(2026, 10, 14, 14, 0))
    assert ok_w, "早餐时段应可用"
    assert not no_w, "非早餐时段应不可用"
    assert "时段" in why, f"应提示时段限制，实际：{why}"


def test_single_stack_policy_keeps_best():
    """一单一张券策略下，保留节省最多的一张。"""
    menu = load_menu()
    c_small = Coupon("S1", "小优惠", "special",
                     product_codes=frozenset({"4810"}), coupon_price=12.0)
    c_big = Coupon("S2", "大优惠", "special",
                   product_codes=frozenset({"1100"}), coupon_price=20.0)
    q = price_basket([("4810", 1), ("1100", 1)], menu, [c_small, c_big],
                     now=MON_2PM, stack_policy=STACK_SINGLE)
    # 薯条省 1.5，巨无霸省 5.5 → 应保留巨无霸
    assert q.applied_coupons == ["大优惠"], f"实际应用：{q.applied_coupons}"


def test_greedy_stack_allows_disjoint():
    """贪婪策略下，作用于不同商品的券可同时使用。"""
    menu = load_menu()
    c1 = Coupon("G1", "薯条特价", "special",
                product_codes=frozenset({"4810"}), coupon_price=10.0)
    c2 = Coupon("G2", "汉堡特价", "special",
                product_codes=frozenset({"1100"}), coupon_price=20.0)
    q = price_basket([("4810", 1), ("1100", 1)], menu, [c1, c2],
                     now=MON_2PM, stack_policy=STACK_GREEDY)
    assert len(q.applied_coupons) == 2
    assert q.paid_total == 30.0


def test_quantity_merging():
    """同商品多行应合并计价。"""
    menu = load_menu()
    q = price_basket([("9900008751", 1), ("9900008751", 3)], menu, [], now=MON_2PM)
    assert len(q.lines) == 1
    assert q.lines[0].qty == 4
    assert q.paid_total == 38.0


def test_zero_and_negative_qty_ignored():
    menu = load_menu()
    q = price_basket([("1100", 0), ("4810", -2)], menu, [], now=MON_2PM)
    assert q.lines == []
    assert q.paid_total == 0.0


def test_unknown_code_warns():
    menu = load_menu()
    q = price_basket([("NOT_EXIST", 1)], menu, [], now=MON_2PM)
    assert any("未找到商品编码" in n for n in q.notes)


def test_scope_filter():
    """外送不可用的券，在到店场景不应被排除；反之亦然。"""
    menu = load_menu()
    dine_only = Coupon("D1", "仅到店", "special",
                       product_codes=frozenset({"4810"}),
                       coupon_price=8.0, scopes=frozenset({"dine_in"}))
    q_dine = price_basket([("4810", 1)], menu, [dine_only],
                          now=MON_2PM, scope="dine_in")
    q_deliv = price_basket([("4810", 1)], menu, [dine_only],
                           now=MON_2PM, scope="delivery")
    assert q_dine.applied_coupons == ["仅到店"]
    assert q_deliv.applied_coupons == []
    assert any("不适用" in n for n in q_deliv.notes)


# --------------------------------------------------------------------------- #
# 券冲突判定
# --------------------------------------------------------------------------- #

def test_conflict_same_product():
    a = Coupon("A", "券A", "special", product_codes=frozenset({"1100"}))
    b = Coupon("B", "券B", "special", product_codes=frozenset({"1100"}))
    assert conflict_reason(a, b) is not None


def test_no_conflict_disjoint_products():
    a = Coupon("A", "券A", "special", product_codes=frozenset({"1100"}))
    b = Coupon("B", "券B", "special", product_codes=frozenset({"4810"}))
    assert conflict_reason(a, b) is None


def test_conflict_two_global():
    g1 = Coupon("G1", "满减", "threshold", threshold=30, discount_amount=5)
    g2 = Coupon("G2", "折扣", "discount", discount_rate=0.9)
    assert conflict_reason(g1, g2) is not None


def test_conflict_global_vs_specific():
    g = Coupon("G1", "全场", "threshold", threshold=30, discount_amount=5)
    s = Coupon("S1", "单品", "special", product_codes=frozenset({"1100"}))
    assert conflict_reason(g, s) is not None


def test_conflict_same_coupon():
    a = Coupon("A", "券A", "special", product_codes=frozenset({"1100"}))
    assert conflict_reason(a, a) is not None


def test_can_stack_three():
    a = Coupon("A", "A", "special", product_codes=frozenset({"1100"}))
    b = Coupon("B", "B", "special", product_codes=frozenset({"4810"}))
    c = Coupon("C", "C", "special", product_codes=frozenset({"9900008751"}))
    ok, _ = can_stack([a, b, c])
    assert ok


# --------------------------------------------------------------------------- #
# 帕累托前沿
# --------------------------------------------------------------------------- #

def test_pareto_frontier_basic():
    """前沿上的点必须两两互不支配。"""
    items = load_dataset()
    front = pareto_frontier(items, max_kcal=900, max_size=3, limit=40)
    assert front, "应返回至少一个前沿点"
    for i, (pt_a, _) in enumerate(front):
        for pt_b, _ in front[i + 1:]:
            dominated = (pt_a.kcal >= pt_b.kcal and pt_a.sodium_mg >= pt_b.sodium_mg
                         and (pt_a.kcal > pt_b.kcal or pt_a.sodium_mg > pt_b.sodium_mg))
            assert not dominated, "前沿点不应存在支配关系"


def test_pareto_frontier_is_sorted():
    """前沿按钠含量升序或热量升序排列，便于阅读。"""
    items = load_dataset()
    front = pareto_frontier(items, max_kcal=900, max_size=2, limit=20)
    values = [t.sodium_mg for t, _ in front]
    assert values == sorted(values), "前沿应按钠升序"


def test_pareto_frontier_respects_bounds():
    items = load_dataset()
    front = pareto_frontier(items, max_kcal=600, max_sodium_mg=800,
                            max_size=3, limit=20)
    for t, _ in front:
        assert t.kcal <= 600
        assert t.sodium_mg <= 800


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