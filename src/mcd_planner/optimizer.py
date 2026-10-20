# -*- coding: utf-8 -*-
"""
套餐优化器：价格 × 钠 的联合求解

这是本项目的核心差异化模块。

参考项目做的是「价格 × 热量」的帕累托前沿，本模块做的是「价格 × 钠」——
同一个方法论，换到医学上更值得关注的维度：中国居民钠摄入普遍超标
（《中国居民膳食指南》建议每日食盐 <5g，约合钠 2000mg），
而一份巨无霸的钠含量就接近 1000mg。

职责分工
--------
pricing.py  负责「这一篮多少钱」（券、叠加、时段）
solver.py   负责「这一篮有多少钠」（营养合计、约束求解）
本模块      负责把两者接起来，在二维空间里求不可支配解集
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Sequence

from .pricing import (
    Coupon, MenuItem, Quote, load_coupons, load_menu, price_basket,
)
from .solver import NutritionItem, load_dataset

# --------------------------------------------------------------------------- #
# 数据装配
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PricedNutritionItem:
    """同时具备价格与营养的餐品。"""

    code: str
    name: str
    price: float
    original_price: float
    category: str
    kcal: float
    sodium_mg: float
    protein_g: float
    fat_g: float
    carb_g: float
    calcium_mg: float


def build_joint_catalog(menu_path=None, nutrition_path=None,
                        map_path=None) -> list[PricedNutritionItem]:
    """
    装配「价格 + 营养」联合目录。

    只保留在营养数据中能明确对应的商品；匹配依据是
    data/menu_nutrition_map.json 中的显式映射。
    """
    import json
    from pathlib import Path

    menu = load_menu(menu_path)
    nutrition = {n.name: n for n in load_dataset(nutrition_path)}

    if map_path is None:
        map_path = (Path(__file__).resolve().parent.parent.parent
                    / "data" / "menu_nutrition_map.json")
    raw_map = json.loads(Path(map_path).read_text(encoding="utf-8"))["map"]

    out: list[PricedNutritionItem] = []
    for code, nut_name in raw_map.items():
        item = menu.get(code)
        nut = nutrition.get(nut_name)
        if item is None or nut is None:
            continue
        out.append(PricedNutritionItem(
            code=item.code, name=item.name,
            price=item.price, original_price=item.original_price,
            category=item.category,
            kcal=nut.kcal, sodium_mg=nut.sodium_mg,
            protein_g=nut.protein_g, fat_g=nut.fat_g,
            carb_g=nut.carb_g, calcium_mg=nut.calcium_mg,
        ))
    return out


# --------------------------------------------------------------------------- #
# 组合与求解
# --------------------------------------------------------------------------- #

@dataclass
class Plan:
    """一个候选方案：商品组合 + 报价 + 营养合计。"""

    codes: list[str]
    names: list[str]
    quote: Quote
    kcal: float
    sodium_mg: float
    protein_g: float
    fat_g: float
    carb_g: float
    calcium_mg: float

    @property
    def price(self) -> float:
        return self.quote.paid_total

    @property
    def list_price(self) -> float:
        return self.quote.list_total

    @property
    def saving(self) -> float:
        return self.quote.saving

    def label(self) -> str:
        return " + ".join(self.names)


@dataclass
class OptimizeResult:
    """优化输出。"""

    plans: list[Plan] = field(default_factory=list)
    frontier: list[Plan] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    catalog_size: int = 0


def _combo_stats(catalog: list[PricedNutritionItem],
                 codes: Sequence[str]) -> tuple[float, float, float, float, float, float]:
    """累加一组商品的营养。"""
    idx = {c.code: c for c in catalog}
    kcal = sod = pro = fat = carb = cal = 0.0
    for code in codes:
        it = idx[code]
        kcal += it.kcal
        sod += it.sodium_mg
        pro += it.protein_g
        fat += it.fat_g
        carb += it.carb_g
        cal += it.calcium_mg
    return kcal, sod, pro, fat, carb, cal


def optimize(
    budget: float | None = None,
    max_sodium_mg: float | None = None,
    max_kcal: float | None = None,
    min_protein_g: float | None = None,
    max_items: int = 3,
    require_staple: bool = True,
    now=None,
    scope: str = "dine_in",
    menu_path=None,
    nutrition_path=None,
    map_path=None,
    coupons: list[Coupon] | None = None,
) -> OptimizeResult:
    """
    在预算与营养约束下，枚举可行组合并求价格 × 钠的帕累托前沿。

    require_staple: 要求组合中至少含一件主食（汉堡/套餐），
                    避免给出「三杯可乐」式方案。
    """
    catalog = build_joint_catalog(menu_path, nutrition_path, map_path)
    result = OptimizeResult(catalog_size=len(catalog))
    if not catalog:
        result.notes.append("联合目录为空，请检查数据文件与映射表")
        return result

    menu = load_menu(menu_path)
    if coupons is None:
        coupons = load_coupons()

    # 单件已超约束的直接剔除
    pool = []
    for it in catalog:
        if max_sodium_mg is not None and it.sodium_mg > max_sodium_mg:
            continue
        if max_kcal is not None and it.kcal > max_kcal:
            continue
        if budget is not None and it.price > budget:
            continue
        pool.append(it)

    # 预算有限时不必遍历全部：按价格升序保留前 N 个
    pool.sort(key=lambda x: (x.price, x.sodium_mg))

    staple_cats = {"burger", "set"}
    candidates: list[Plan] = []

    for size in range(1, max_items + 1):
        for combo in combinations(pool, size):
            codes = [c.code for c in combo]
            cats = {c.category for c in combo}
            if require_staple and not (cats & staple_cats):
                continue
            kcal, sod, pro, fat, carb, cal = _combo_stats(catalog, codes)
            if max_kcal is not None and kcal > max_kcal:
                continue
            if max_sodium_mg is not None and sod > max_sodium_mg:
                continue
            if min_protein_g is not None and pro < min_protein_g:
                continue

            quote = price_basket([(c, 1) for c in codes], menu, coupons,
                                 now=now, scope=scope)
            if budget is not None and quote.paid_total > budget:
                continue

            candidates.append(Plan(
                codes=codes,
                names=[c.name for c in combo],
                quote=quote,
                kcal=kcal, sodium_mg=sod, protein_g=pro,
                fat_g=fat, carb_g=carb, calcium_mg=cal,
            ))

    if not candidates:
        result.notes.append("没有组合满足当前约束，尝试放宽预算或钠上限")
        return result

    # 帕累托：价格 × 钠 双目标最小化
    candidates.sort(key=lambda p: (p.price, p.sodium_mg))
    best_sodium = float("inf")
    for p in candidates:
        if p.sodium_mg < best_sodium - 1e-9:
            result.frontier.append(p)
            best_sodium = p.sodium_mg

    # 主榜单：同等价格下钠更低，按「性价比」排序
    candidates.sort(key=lambda p: (p.price, p.sodium_mg))
    result.plans = candidates
    return result


def format_frontier(frontier: list[Plan]) -> str:
    """把帕累托前沿渲染成可读文本。"""
    if not frontier:
        return "（无可行解）"
    lines = []
    lines.append(f"{'实付':>7}  {'钠':>7}  {'热量':>7}  组合")
    lines.append("-" * 62)
    for p in frontier:
        lines.append(f"{p.price:>7.2f}  {p.sodium_mg:>6.0f}mg  "
                     f"{p.kcal:>6.0f}kcal  {p.label()}")
    return "\n".join(lines)


def describe_tradeoff(frontier: list[Plan]) -> str:
    """用一句话说明前沿两端的取舍。"""
    if len(frontier) < 2:
        return ""
    cheapest = frontier[0]
    lowest_sodium = min(frontier, key=lambda p: p.sodium_mg)
    d_price = lowest_sodium.price - cheapest.price
    d_sodium = cheapest.sodium_mg - lowest_sodium.sodium_mg
    if d_sodium <= 0:
        return "本场景下最低价与最低钠恰好是同一方案。"
    return (f"最省 ¥{cheapest.price:.2f}（钠 {cheapest.sodium_mg:.0f}mg）→ "
            f"最低钠 {lowest_sodium.sodium_mg:.0f}mg"
            f"（¥{lowest_sodium.price:.2f}），"
            f"多花 ¥{d_price:.2f} 可减钠 {d_sodium:.0f}mg")


def dominating_alternatives(
    target_code: str,
    catalog: list[PricedNutritionItem],
    max_items: int = 3,
    now=None,
    coupons: list[Coupon] | None = None,
    menu_path=None,
) -> list[Plan]:
    """
    找出能「双维度都不差」地替代某个商品的方案。

    这是本模块最实用的一项：用户往往已有明确想吃的单品，
    此时不该硬推别的，而是告诉他「你选的这个，有没有更便宜又更健康的替法」。

    支配判定：价格 ≤ 目标，钠 ≤ 目标，且至少一项严格更优。

    约束：只在**同类**商品中寻找替代。汉堡不能用冰淇淋来替代
    ——价格与钠确实更优，但那不是「替代」，是「换了一顿饭」。
    """
    target = next((c for c in catalog if c.code == target_code), None)
    if target is None:
        return []

    menu = load_menu(menu_path)
    if coupons is None:
        coupons = load_coupons()
    idx = {c.code: c for c in catalog}

    # 同类替代：主食只能在主食内替换，小食只能在小食内替换
    STAPLE = {"burger", "set"}
    target_is_staple = target.category in STAPLE
    same_kind = [c for c in catalog
                 if c.code != target_code
                 and ((c.category in STAPLE) == target_is_staple)]

    # 单项已能支配的直接返回
    results: list[Plan] = []
    for it in same_kind:
        if it.price <= target.price and it.sodium_mg <= target.sodium_mg:
            if it.price < target.price or it.sodium_mg < target.sodium_mg:
                quote = price_basket([(it.code, 1)], menu, coupons,
                                     now=now, scope="dine_in")
                results.append(Plan(
                    codes=[it.code], names=[it.name], quote=quote,
                    kcal=it.kcal, sodium_mg=it.sodium_mg,
                    protein_g=it.protein_g, fat_g=it.fat_g,
                    carb_g=it.carb_g, calcium_mg=it.calcium_mg,
                ))

    # 组合替代：仅当目标是主食时，考虑「主食 + 饮品」的组合
    if max_items >= 2 and target_is_staple:
        staples = [c for c in same_kind if c.category in STAPLE]
        fillers = [c for c in catalog if c.category not in STAPLE
                   and c.price <= 12]
        staples.sort(key=lambda x: (x.price, x.sodium_mg))
        fillers.sort(key=lambda x: (x.price, x.sodium_mg))
        for st in staples[:8]:
            for fl in fillers[:4]:
                price_sum = st.price + fl.price
                if price_sum > target.price:
                    continue
                sod = st.sodium_mg + fl.sodium_mg
                if sod > target.sodium_mg:
                    continue
                codes = [st.code, fl.code]
                quote = price_basket([(c, 1) for c in codes], menu, coupons,
                                     now=now, scope="dine_in")
                results.append(Plan(
                    codes=codes, names=[st.name, fl.name], quote=quote,
                    kcal=st.kcal + fl.kcal, sodium_mg=sod,
                    protein_g=st.protein_g + fl.protein_g,
                    fat_g=st.fat_g + fl.fat_g,
                    carb_g=st.carb_g + fl.carb_g,
                    calcium_mg=st.calcium_mg + fl.calcium_mg,
                ))

    # 去重并按「省了多少 + 减了多少钠」综合排序
    seen: set[tuple[str, ...]] = set()
    deduped: list[Plan] = []
    for p in results:
        key = tuple(sorted(p.codes))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    deduped.sort(key=lambda p: (p.price, p.sodium_mg))
    return deduped[:8]


def explain_dominance(target: PricedNutritionItem, alt: Plan) -> str:
    """用一句话说明替代关系省了什么。"""
    d_price = target.price - alt.price
    d_sodium = target.sodium_mg - alt.sodium_mg
    bits = []
    if d_price > 0.005:
        bits.append(f"便宜 ¥{d_price:.2f}")
    if d_sodium > 0.5:
        bits.append(f"少钠 {d_sodium:.0f}mg")
    if not bits:
        return "营养与价格持平"
    return "、".join(bits)